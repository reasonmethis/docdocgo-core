import os
import random
from datetime import datetime
from enum import Enum
from typing import Callable

from chromadb import ClientAPI
from langchain.schema import Document
from langchain.utilities.google_serper import GoogleSerperAPIWrapper

from agents.dbmanager import construct_full_collection_name
from agents.websearcher_data import WebsearcherData
from agents.websearcher_quick import get_websearcher_response_quick
from components.chroma_ddg import exists_collection
from components.llm import get_prompt_llm_chain
from utils.async_utils import gather_tasks_sync, make_sync
from utils.chat_state import ChatState
from utils.docgrab import ingest_docs_into_chroma_client
from utils.helpers import DELIMITER, print_no_newline
from utils.lang_utils import (
    get_num_tokens,
    get_num_tokens_in_texts,
    limit_tokens_in_texts,
)
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import (
    ITERATIVE_REPORT_IMPROVER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    WEBSEARCHER_PROMPT_INITIAL_REPORT,
)
from utils.strings import extract_json
from utils.type_utils import ChatMode, OperationMode
from utils.web import (
    LinkData,
    afetch_urls_in_parallel_aiohttp,
    afetch_urls_in_parallel_playwright,
)
from utils.websearcher_utils import get_links


def get_batch_fetcher():
    """Decide which fetcher to use for the links."""
    if not os.getenv("USE_PLAYWRIGHT"):
        return make_sync(afetch_urls_in_parallel_aiohttp)

    def link_fetcher(links):
        return make_sync(afetch_urls_in_parallel_playwright)(
            links, callback=lambda url, html: print_no_newline(".")
        )

    return link_fetcher


def get_content_from_urls_with_top_up(
    urls: list[str],
    batch_fetcher: Callable[[list[str]], list[str]],
    min_ok_urls: int,
    init_batch_size: int,
) -> dict[str, LinkData]:
    """
    Fetch content from a list of urls using a batch fetcher. If at least
    min_ok_urls urls are fetched successfully, return the fetched content.
    Otherwise, fetch a new batch of urls, and repeat until at least min_ok_urls
    urls are fetched successfully.
    """
    print(
        f"Fetching content from {len(urls)} urls:\n"
        f" - {min_ok_urls} successfully obtained URLs needed\n"
        f" - {init_batch_size} is the initial batch size\n"
    )

    link_data_dict = {}
    num_urls = len(urls)
    num_processed_urls = 0
    num_ok_urls = 0

    # If, say, only 3 ok urls are still needed, we might want to try fetching 3 + extra
    num_extras = max(2, init_batch_size - min_ok_urls)

    while num_processed_urls < num_urls and num_ok_urls < min_ok_urls:
        batch_size = min(
            init_batch_size,
            num_urls - num_processed_urls,
            min_ok_urls - num_ok_urls + num_extras,
        )
        print(f"Fetching {batch_size} urls:")
        batch_urls = urls[num_processed_urls : num_processed_urls + batch_size]
        print("- " + "\n- ".join(batch_urls))

        # Fetch content from urls in batch
        batch_htmls = batch_fetcher(batch_urls)

        # Process fetched content
        for url, html in zip(batch_urls, batch_htmls):
            link_data = LinkData.from_html(html)
            if not link_data.error:
                num_ok_urls += 1
            link_data_dict[url] = link_data
        num_processed_urls += batch_size

        print(f"Total URLs processed: {num_processed_urls} ({num_urls} total)")
        print(f"Total successful URLs: {num_ok_urls} ({min_ok_urls} needed)\n")

    return link_data_dict


REPORT_ASSESSMENT_MSG = "REPORT ASSESSMENT:"
NO_IMPROVEMENT_MSG = "NO IMPROVEMENT, PREVIOUS REPORT ASSESSMENT:"
ACTION_ITEMS_MSG = "ACTION ITEMS FOR IMPROVEMENT:"
NEW_REPORT_MSG = "NEW REPORT:"


def parse_iterative_report(answer: str) -> tuple[str, str | None]:
    """
    Parse the answer from an iterative researcher response and return the
    report and the LLM's assessment of the report.
    """
    # Extract and record the report and the LLM's assessment of the report
    idx_suggestions = answer.find(ACTION_ITEMS_MSG)
    idx_new_report = answer.find(NEW_REPORT_MSG)
    idx_assessment = answer.rfind(REPORT_ASSESSMENT_MSG)

    # Determine the start of the report (and end of suggestions if present)
    if -1 < idx_suggestions < idx_new_report:
        # SUGGESTIONS and NEW REPORT found
        idx_start_report = idx_new_report + len(NEW_REPORT_MSG)
    else:
        # No suggestions found. Identify the start of the report by "#" if present
        idx_start_report = answer.find("#")
        if idx_start_report == -1:
            # No "#" found, so the report starts at the beginning of the answer
            idx_start_report = 0

    # Determine the end of the report and the start of the evaluation
    if idx_assessment == -1:
        # Something went wrong, we will return evaluation = None
        idx_end_report = len(answer)
        evaluation = None
    else:
        # Determine which of the two evaluations we got
        length_diff = len(NO_IMPROVEMENT_MSG) - len(REPORT_ASSESSMENT_MSG)
        idx_no_improvement = idx_assessment - length_diff
        if (
            idx_no_improvement >= 0
            and answer[
                idx_no_improvement : idx_no_improvement + len(NO_IMPROVEMENT_MSG)
            ]
            == NO_IMPROVEMENT_MSG
        ):
            # No improvement string found
            idx_end_report = idx_no_improvement
        else:
            # Improvement
            idx_end_report = idx_assessment
        evaluation = answer[idx_end_report:]

    report = answer[idx_start_report:idx_end_report].strip()
    return report, evaluation


MAX_QUERY_GENERATOR_ATTEMPTS = 5
DEFAULT_MAX_TOKENS_FINAL_CONTEXT = int(CONTEXT_LENGTH * 0.7)
DEFAULT_MAX_TOTAL_LINKS = round(DEFAULT_MAX_TOKENS_FINAL_CONTEXT / 1600)
# TODO: experiment with reducing the number of sources (gpt-3.5 may have trouble with 7)


def get_websearcher_response_medium(
    chat_state: ChatState,
    max_queries: int = 7,
    max_total_links: int = DEFAULT_MAX_TOTAL_LINKS,
    max_tokens_final_context: int = DEFAULT_MAX_TOKENS_FINAL_CONTEXT,
):
    query = chat_state.message
    # Get queries to search for using query generator prompt
    query_generator_chain = get_prompt_llm_chain(
        QUERY_GENERATOR_PROMPT,
        llm_settings=chat_state.bot_settings,
    )
    for i in range(MAX_QUERY_GENERATOR_ATTEMPTS):
        try:
            query_generator_output = "OUTPUT_FAILED"
            query_generator_output = query_generator_chain.invoke(
                {
                    "query": query,
                    "timestamp": datetime.now().strftime("%A, %B %d, %Y, %I:%M %p"),
                    # "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            )
            print(f"Attempt {i + 1}: {query_generator_output = }")
            query_generator_dict = extract_json(query_generator_output)
            queries = query_generator_dict["queries"][:max_queries]
            report_type = query_generator_dict["report_type"]
            break
        except Exception as e:
            print(
                f"Failed to generate queries on attempt {i + 1}/"
                f"{MAX_QUERY_GENERATOR_ATTEMPTS}. Error: \n{e}"
            )
            err_msg = (
                "Failed to generate queries. Query generator output:\n\n"
                f"{query_generator_output}\n\nError: {e}"
            )
    else:
        raise Exception(err_msg)

    print("Generated queries:", repr(queries).strip("[]"))
    print("Report type will be:", repr(report_type))

    try:
        # Do a Google search for each query
        print("Fetching search result links for each query...")
        num_search_results = (
            100
            if chat_state.chat_mode == ChatMode.ITERATIVE_RESEARCH_COMMAND_ID
            else 10
        )  # default is 10; 20-100 costs 2 credits per query
        search = GoogleSerperAPIWrapper(k=num_search_results)
        search_tasks = [search.aresults(query) for query in queries]
        search_results = gather_tasks_sync(search_tasks)  # TODO serper has batching

        # Get links from search results
        all_links = get_links(search_results)
        print(
            f"Got {len(all_links)} links in total, "
            f"will fetch *at least* {min(max_total_links, len(all_links))}:\n-",
            "\n- ".join(all_links[:max_total_links]),
        )
        t_get_links_end = datetime.now()
    except Exception as e:
        raise ValueError(f"Failed to get links: {e}")

    try:
        print("Fetching content from links and extracting main content...")

        # Get content from links
        link_data_dict = get_content_from_urls_with_top_up(
            all_links,
            batch_fetcher=get_batch_fetcher(),
            min_ok_urls=round(max_total_links * 0.75),
            init_batch_size=max_total_links,
        )
        print()
    except Exception as e:
        raise ValueError(f"Failed to fetch content from URLs: {e}")

    # Initialize data object
    processed_links = list(link_data_dict.keys())
    ws_data = WebsearcherData(
        query=query,
        generated_queries=queries,
        report_type=report_type,
        unprocessed_links=all_links[len(processed_links) :],
        processed_links=processed_links,
        link_data_dict=link_data_dict,
        max_tokens_final_context=max_tokens_final_context,
    )

    # Get a list of acceptably fetched links and their texts
    links = [link for link, data in link_data_dict.items() if not data.error]
    texts = [link_data_dict[link].text for link in links]
    t_process_texts_end = datetime.now()

    try:
        print("Constructing final context...")
        final_texts, final_token_counts = limit_tokens_in_texts(
            texts,
            max_tokens_final_context,
        )
        final_texts = [
            f"SOURCE: {link}\nCONTENT:\n{text}\n====="
            for text, link in zip(final_texts, links)
        ]
        final_context = "\n\n".join(final_texts)
        t_final_context = datetime.now()

        print("Number of obtained links:", len(all_links))
        print("Number of processed links:", len(ws_data.processed_links))
        print("Number of links after removing unsuccessfully fetched ones:", len(links))
        print("Time taken to process links:", t_process_texts_end - t_get_links_end)
        print("Time taken to shorten texts:", t_final_context - t_process_texts_end)
        print("Number of tokens in final context:", get_num_tokens(final_context))

        print("\nGenerating report...\n")
        chain = get_prompt_llm_chain(
            WEBSEARCHER_PROMPT_INITIAL_REPORT,
            # WEBSEARCHER_PROMPT_DYNAMIC_REPORT,
            llm_settings=chat_state.bot_settings,
            print_prompt=bool(os.getenv("PRINT_WEBSEARCHER_PROMPT")),
            callbacks=chat_state.callbacks,
            stream=True,
        )
        answer = chain.invoke(
            {"texts_str": final_context, "query": query, "report_type": report_type}
        )
        ws_data.report, ws_data.evaluation = parse_iterative_report(answer)

        return {"answer": answer, "ws_data": ws_data, "source_links": links}
    except Exception as e:
        texts_str = "\n\n".join(x[:200] for x in texts)
        print(f"Failed to get report: {e}, texts:\n\n{texts_str}")
        raise ValueError(f"Failed to generate report: {e}")


SMALL_WORDS = {"a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or"}
SMALL_WORDS |= {"is", "are", "was", "were", "be", "been", "being", "am", "what"}
SMALL_WORDS |= {"which", "who", "whom", "whose", "where", "when", "how"}
SMALL_WORDS |= {"this", "that", "these", "those", "there", "here", "can", "could"}
SMALL_WORDS |= {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her"}


def get_initial_iterative_researcher_response(
    chat_state: ChatState,
) -> WebsearcherData:
    response = get_websearcher_response_medium(chat_state)
    ws_data: WebsearcherData = response["ws_data"]

    # Determine which links to include in the db
    links_to_include = [
        link for link, data in ws_data.link_data_dict.items() if not data.error
    ]
    # if not links_to_include:
    #     return ws_data
    # NOTE: should work even if there are no links to include, but might want to test

    # Decide on the collection name consistent with ChromaDB's naming rules
    query_words = [x.lower() for x in ws_data.query.split()]
    words = []
    words_excluding_small = []
    for word in query_words:
        word_just_alnum = "".join(x for x in word if x.isalnum())
        if not word_just_alnum:
            break
        words.append(word_just_alnum)
        if word not in SMALL_WORDS:
            words_excluding_small.append(word_just_alnum)

    words = words_excluding_small if len(words_excluding_small) > 2 else words

    new_coll_name = "-".join(words[:3])[:35].rstrip("-")
    new_coll_name = construct_full_collection_name(chat_state.user_id, new_coll_name)

    if len(new_coll_name) < 3:
        # Can only happen for a public collection (no prefixed user_id)
        new_coll_name = f"collection-{new_coll_name}".rstrip("-")

    ws_data.collection_name = new_coll_name

    # Check if collection exists, if so, add a number to the end
    chroma_client: ClientAPI = chat_state.vectorstore._client
    for i in range(2, 1000000):
        if not exists_collection(ws_data.collection_name, chroma_client):
            break
        ws_data.collection_name = f"{new_coll_name}-{i}"

    # Convert website content into documents for ingestion
    print()  # we just printed the report, so add a newline
    print_no_newline("Ingesting fetched content into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_include:
        link_data = ws_data.link_data_dict[link]
        metadata = {"source": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    for i in range(2):
        try:
            collection_metadata = {"ws_data": ws_data.json()}
            # NOTE: might want to remove collection_name from collection_metadata
            # since the user can rename the collection without updating the metadata
            ingest_docs_into_chroma_client(
                docs,
                ws_data.collection_name,
                chroma_client,
                collection_metadata=collection_metadata,
            )
            break  # success
        except Exception as e:  # bad name error may not be ValueError in docker mode
            if i or "Expected collection name" not in str(e):
                raise e  # i == 1 means tried normal name and random name, give up

            # Create a random valid collection name and try again
            ws_data.collection_name = construct_full_collection_name(
                chat_state.user_id,
                "collection-" + "".join(random.sample("abcdefghijklmnopqrstuvwxyz", 6)),
            )
    print("Done!")
    return response  # has answer, ws_data


NUM_NEW_OK_LINKS_TO_PROCESS = 2
INIT_BATCH_SIZE = 4


def get_iterative_researcher_response(
    chat_state: ChatState,
) -> WebsearcherData:
    if chat_state.message:
        # No need to get ws_data from the database, since we are starting a new research
        ws_data = None
    else:
        ws_data: WebsearcherData = chat_state.ws_data  # NOTE: might want to convert to
        # chat_state.get_ws_data() for readability

    # Special handling for first iteration
    if not ws_data or not ws_data.report:
        return get_initial_iterative_researcher_response(chat_state)

    t_start = datetime.now()
    print("Current version of report:\n", ws_data.report)
    print(DELIMITER)
    print("Processed links:\n- " + "\n- ".join(ws_data.processed_links))
    # Sanity check
    if (
        sum(
            1
            for link in ws_data.unprocessed_links[
                : ws_data.num_obtained_unprocessed_links
            ]
            if not ws_data.link_data_dict[link].error
        )
        != ws_data.num_obtained_unprocessed_ok_links
    ):
        raise ValueError("Mismatch in the number of obtained unprocessed good links")

    # Get content from more links if needed
    num_ok_new_links_to_fetch = (
        NUM_NEW_OK_LINKS_TO_PROCESS - ws_data.num_obtained_unprocessed_ok_links
    )
    if num_ok_new_links_to_fetch > 0:
        link_data_dict = get_content_from_urls_with_top_up(
            ws_data.unprocessed_links[ws_data.num_obtained_unprocessed_links :],
            batch_fetcher=get_batch_fetcher(),
            min_ok_urls=num_ok_new_links_to_fetch,
            init_batch_size=INIT_BATCH_SIZE,
        )

        # Update ws_data
        ws_data.link_data_dict.update(link_data_dict)
        ws_data.num_obtained_unprocessed_links += len(link_data_dict)

        tmp = sum(1 for data in link_data_dict.values() if not data.error)
        ws_data.num_obtained_unprocessed_ok_links += tmp
        print()
    t_fetch_end = datetime.now()

    # Prepare links to include in the context (only good links)
    links_to_include = []
    links_to_count_tokens_for = []
    num_links_to_include = 0
    num_new_processed_links = 0
    for link in ws_data.unprocessed_links:
        # Stop if have enough links; consider only *obtained* links
        if (
            num_links_to_include == NUM_NEW_OK_LINKS_TO_PROCESS
            or num_new_processed_links == ws_data.num_obtained_unprocessed_links
        ):
            break
        num_new_processed_links += 1

        # Include link if it's good
        if ws_data.link_data_dict[link].error:
            continue
        links_to_include.append(link)
        num_links_to_include += 1

        # Check if we need to count tokens for this link
        if ws_data.link_data_dict[link].num_tokens is None:
            links_to_count_tokens_for.append(link)

    texts_to_include = [ws_data.link_data_dict[x].text for x in links_to_include]

    # Update ws_data once again to reflect the links about to be processed
    ws_data.processed_links += ws_data.unprocessed_links[:num_new_processed_links]
    ws_data.unprocessed_links = ws_data.unprocessed_links[num_new_processed_links:]
    ws_data.num_obtained_unprocessed_links -= num_new_processed_links
    ws_data.num_obtained_unprocessed_ok_links -= num_links_to_include

    # If no links to include, don't submit to LLM
    if not links_to_include:
        # Save new ws_data in chat_state (which saves it in the database) and return
        chat_state.save_ws_data(ws_data)
        return {
            "answer": "There are no more usable sources to incorporate into the report",
            "ws_data": ws_data,
            "needs_print": True,  # NOTE: this won't be streamed
        }

    # Count tokens in texts to be processed; throw in the report text too
    print("Counting tokens in texts and current report...")
    texts_to_count_tokens_for = [
        ws_data.link_data_dict[x].text for x in links_to_count_tokens_for
    ] + [ws_data.report]
    token_counts = get_num_tokens_in_texts(texts_to_count_tokens_for)

    num_tokens_report = token_counts[-1]
    for link, num_tokens in zip(links_to_count_tokens_for, token_counts):
        ws_data.link_data_dict[link].num_tokens = num_tokens

    # Shorten texts that are too long and construct combined sources text
    # TODO consider chunking and/or reducing num of included links instead
    print("Constructing final context...")
    final_texts, final_token_counts = limit_tokens_in_texts(
        texts_to_include,
        ws_data.max_tokens_final_context - num_tokens_report,
        cached_token_counts=[
            ws_data.link_data_dict[x].num_tokens for x in links_to_include
        ],
    )
    final_texts = [
        f"SOURCE: {link}\nCONTENT:\n{text}\n====="
        for text, link in zip(final_texts, links_to_include)
    ]  # NOTE: this adds a bit of extra tokens to the final context but it's ok
    final_context = "\n\n".join(final_texts)
    t_construct_context_end = datetime.now()

    print("Time taken to fetch sites:", t_fetch_end - t_start)
    print("Time taken to process texts:", t_construct_context_end - t_fetch_end)
    if chat_state.operation_mode == OperationMode.CONSOLE:
        num_tokens_final_context = get_num_tokens(final_context)  # NOTE rm to save time
        print("Number of resulting tokens in the context:", num_tokens_final_context)
        print(
            "Number of resulting tokens in the context + report:",
            num_tokens_report + num_tokens_final_context,
        )

    # Submit to LLM to generate report
    print("Generating report...\n")
    chain = get_prompt_llm_chain(
        ITERATIVE_REPORT_IMPROVER_PROMPT,
        llm_settings=chat_state.bot_settings,
        print_prompt=bool(os.getenv("PRINT_WEBSEARCHER_PROMPT")),
        callbacks=chat_state.callbacks,
        stream=True,
    )
    inputs = {
        "new_info": final_context,
        "query": ws_data.query,
        "previous_report": ws_data.report,
    }
    if "report_type" in ITERATIVE_REPORT_IMPROVER_PROMPT.input_variables:
        inputs["report_type"] = ws_data.report_type

    answer = chain.invoke(inputs)

    # Extract and record the report and the LLM's assessment of the report
    ws_data.report, ws_data.evaluation = parse_iterative_report(answer)

    # Prepare new documents for ingestion
    # NOTE: links_to_include is non-empty if we got here
    print()  # we just printed the report, so add a newline
    print("Ingesting new documents into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_include:
        link_data = ws_data.link_data_dict[link]
        metadata = {"source": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    ingest_docs_into_chroma_client(
        docs, ws_data.collection_name, chat_state.vectorstore._client
    )

    # Save new ws_data in chat_state (which saves it in the database) and return
    chat_state.save_ws_data(ws_data)
    return {"answer": answer, "ws_data": ws_data, "source_links": links_to_include}
    # NOTE: look into removing ws_data from the response


class WebsearcherMode(Enum):
    QUICK = 1
    MEDIUM = 2
    TEST = 3


def get_websearcher_response(chat_state: ChatState, mode=WebsearcherMode.MEDIUM):
    if mode == WebsearcherMode.QUICK:
        return get_websearcher_response_quick(chat_state)
    elif mode == WebsearcherMode.MEDIUM:
        return get_websearcher_response_medium(chat_state)
    elif mode == WebsearcherMode.TEST:
        return get_websearcher_response_medium(chat_state)
        # return get_web_test_response(chat_state)
    raise ValueError(f"Invalid mode: {mode}")

    # Snippet for contextual compression

    # if False:  # skip contextual compression (loses info, at least with GPT-3.5)
    #     print("Counting tokens in texts...")
    #     max_tokens_per_text, token_counts = get_max_token_allowance_for_texts(
    #         texts, max_tokens_final_context
    #     )  # final context will include extra tokens for separators, links, etc.

    #     print(
    #         f"Removing irrelevant parts from texts that have over {max_tokens_per_text} tokens..."
    #     )
    #     new_texts = []
    #     new_token_counts = []
    #     for text, link, num_tokens in zip(texts, links, token_counts):
    #         if num_tokens <= max_tokens_per_text:
    #             # Don't summarize short texts
    #             print("KEEPING:", link, "(", num_tokens, "tokens )")
    #             new_texts.append(text)
    #             new_token_counts.append(num_tokens)
    #             continue
    #         # If it's way too long, first just shorten it mechanically
    #         # NOTE: can instead chunk it
    #         if num_tokens > max_tokens_final_context:
    #             text = limit_tokens_in_text(
    #                 text, max_tokens_final_context, slow_down_factor=0
    #             )
    #         print("SHORTENING:", link)
    #         print("CONTENT:", text)
    #         print(DELIMITER)
    #         chain = get_prompt_llm_chain(
    #             SUMMARIZER_PROMPT, init_str=f"SHORTENED TEXT FROM {link}: ", stream=True
    #         )
    #         try:
    #             new_text = chain.invoke({"text": text, "query": query})
    #         except Exception as e:
    #             new_text = "<ERROR WHILE GENERATING CONTENT>"
    #         num_tokens = get_num_tokens(new_text)
    #         new_texts.append(new_text)
    #         new_token_counts.append(num_tokens)
    #         print(DELIMITER)
    #     texts, token_counts = new_texts, new_token_counts
    # else:
    #     token_counts = None  # to make limit_tokens_in_texts() work either way
