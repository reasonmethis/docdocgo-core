import os
import random
from datetime import datetime
from enum import Enum
from typing import Callable

from chromadb import ClientAPI
from langchain.schema import Document
from langchain.utilities.google_serper import GoogleSerperAPIWrapper

from agents.dbmanager import (
    construct_full_collection_name,
    get_user_facing_collection_name,
)
from agents.researcher_data import Report, ResearchReportData
from agents.websearcher_quick import get_websearcher_response_quick
from components.chroma_ddg import exists_collection
from components.llm import get_prompt_llm_chain
from utils.async_utils import gather_tasks_sync, make_sync
from utils.chat_state import ChatState
from utils.docgrab import ingest_docs_into_chroma_client
from utils.helpers import (
    DELIMITER,
    RESEARCH_COMMAND_HELP_MESSAGE,
    format_invalid_input_answer,
    format_nonstreaming_answer,
    print_no_newline,
)
from utils.lang_utils import (
    get_num_tokens,
    get_num_tokens_in_texts,
    limit_tokens_in_texts,
)
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import (
    ITERATIVE_REPORT_IMPROVER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    REPORT_COMBINER_PROMPT,
    RESEARCHER_PROMPT_INITIAL_REPORT,
)
from utils.query_parsing import ParsedQuery, ResearchCommand
from utils.researcher_utils import get_links
from utils.strings import extract_json
from utils.type_utils import ChatMode, OperationMode, Props
from utils.web import (
    LinkData,
    afetch_urls_in_parallel_aiohttp,
    afetch_urls_in_parallel_playwright,
)


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
        # Suggestions for improvement and NEW REPORT found
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
NUM_OK_LINKS_NEW_REPORT = min(7, round(DEFAULT_MAX_TOKENS_FINAL_CONTEXT / 1600))
# TODO: experiment with reducing the number of sources (gpt-3.5 may have trouble with 7)


def get_initial_researcher_response(
    chat_state: ChatState,
    max_queries: int = 20,  # not that important (as long as it's not too small)
    num_ok_links: int = NUM_OK_LINKS_NEW_REPORT,
    max_tokens_final_context: int = DEFAULT_MAX_TOKENS_FINAL_CONTEXT,
):
    query = chat_state.message
    # Get queries to search for using query generator prompt
    query_generator_chain = get_prompt_llm_chain(
        QUERY_GENERATOR_PROMPT,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
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
            100 if chat_state.chat_mode == ChatMode.RESEARCH_COMMAND_ID else 10
        )  # default is 10; 20-100 costs 2 credits per query
        search = GoogleSerperAPIWrapper(k=num_search_results)
        search_tasks = [search.aresults(query) for query in queries]
        search_results = gather_tasks_sync(search_tasks)  # TODO serper has batching

        # Get links from search results
        all_links = get_links(search_results)
        print(
            f"Got {len(all_links)} links in total, "
            f"will try to fetch at least {min(num_ok_links, len(all_links))} successfully:\n-",
            "\n- ".join(all_links[:num_ok_links]),  # will fetch more if some fail
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
            min_ok_urls=num_ok_links,
            init_batch_size=min(
                10, round(num_ok_links * 1.2)
            ),  # NOTE: might want to look into best value
        )
        print()
    except Exception as e:
        raise ValueError(f"Failed to fetch content from URLs: {e}")

    # Determine which links to include in the context (num_ok_links good links)
    processed_links = []  # NOTE: might want to rename to links_to_process
    links = []  # NOTE: might want to rename to links_to_include
    for link, data in link_data_dict.items():
        # If we have enough ok links, stop gathering processed links and links to include
        if len(links) == num_ok_links:
            break
        processed_links.append(link)
        if not data.error:
            links.append(link)

    # Initialize data object
    num_obtained_ok_links = sum(1 for data in link_data_dict.values() if not data.error)
    rr_data = ResearchReportData(
        query=query,
        generated_queries=queries,
        report_type=report_type,
        unprocessed_links=all_links[len(processed_links) :],
        processed_links=processed_links,
        num_obtained_unprocessed_links=len(link_data_dict) - len(processed_links),
        num_obtained_unprocessed_ok_links=num_obtained_ok_links - len(links),
        link_data_dict=link_data_dict,
        max_tokens_final_context=max_tokens_final_context,
    )

    # Get a list of acceptably fetched texts
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

        print("Number of discovered links:", len(all_links))
        print("Number of obtained links:", len(link_data_dict))
        print("Number of successfully obtained links:", num_obtained_ok_links)
        print("Number of processed links:", len(rr_data.processed_links))
        print("Number of links after removing unsuccessfully fetched ones:", len(links))
        print("Time taken to process links:", t_process_texts_end - t_get_links_end)
        print("Time taken to shorten texts:", t_final_context - t_process_texts_end)
        print("Number of tokens in final context:", get_num_tokens(final_context))

        print("\nGenerating report...\n")
        chain = get_prompt_llm_chain(
            RESEARCHER_PROMPT_INITIAL_REPORT,
            # RESEARCHER_PROMPT_DYNAMIC_REPORT,
            llm_settings=chat_state.bot_settings,
            api_key=chat_state.openai_api_key,
            print_prompt=bool(os.getenv("PRINT_RESEARCHER_PROMPT")),
            callbacks=chat_state.callbacks,
            stream=True,
        )
        answer = chain.invoke(
            {"texts_str": final_context, "query": query, "report_type": report_type}
        )
        rr_data.main_report, rr_data.evaluation = parse_iterative_report(answer)

        return {"answer": answer, "rr_data": rr_data, "source_links": links}
    except Exception as e:
        texts_str = "\n\n".join(x[:200] for x in texts)
        print(f"Failed to get report: {e}, texts:\n\n{texts_str}")
        raise ValueError(f"Failed to generate report: {e}")


WebsearcherMode = Enum("WebsearcherMode", "QUICK MEDIUM TEST")


def get_websearcher_response(chat_state: ChatState, mode=WebsearcherMode.MEDIUM):
    if mode == WebsearcherMode.QUICK:
        return get_websearcher_response_quick(chat_state)
    elif mode == WebsearcherMode.MEDIUM:
        return get_initial_researcher_response(chat_state)
    elif mode == WebsearcherMode.TEST:
        return get_initial_researcher_response(chat_state)
        # return get_web_test_response(chat_state)
    raise ValueError(f"Invalid mode: {mode}")


SMALL_WORDS = {"a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or"}
SMALL_WORDS |= {"is", "are", "was", "were", "be", "been", "being", "am", "what"}
SMALL_WORDS |= {"what", "which", "who", "whom", "whose", "where", "when", "how"}
SMALL_WORDS |= {"this", "that", "these", "those", "there", "here", "can", "could"}
SMALL_WORDS |= {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her"}
SMALL_WORDS |= {"my", "your", "his", "her", "its", "our", "their", "mine", "yours"}
SMALL_WORDS |= {"some", "any"}


def get_initial_iterative_researcher_response(chat_state: ChatState) -> Props:
    response = get_initial_researcher_response(chat_state)
    rr_data: ResearchReportData = response["rr_data"]

    # Initialize preliminary reports
    # NOTE: might want to store the main report in the same format (Report)
    rr_data.base_reports.append(
        Report(
            report_text=rr_data.main_report,
            sources=response["source_links"],
            evaluation=rr_data.evaluation,
        )
    )

    # Determine which links to include in the db
    links_to_include = [
        link for link, data in rr_data.link_data_dict.items() if not data.error
    ]
    # if not links_to_include:
    #     return rr_data
    # NOTE: should work even if there are no links to include, but might want to test

    # Decide on the collection name consistent with ChromaDB's naming rules
    query_words = [x.lower() for x in rr_data.query.split()]
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

    rr_data.collection_name = new_coll_name

    # Check if collection exists, if so, add a number to the end
    chroma_client: ClientAPI = chat_state.vectorstore._client
    for i in range(2, 1000000):
        if not exists_collection(rr_data.collection_name, chroma_client):
            break
        rr_data.collection_name = f"{new_coll_name}-{i}"

    # Convert website content into documents for ingestion
    print()  # we just printed the report, so add a newline
    print_no_newline("Ingesting fetched content into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_include:
        link_data = rr_data.link_data_dict[link]
        metadata = {"source": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    for i in range(2):
        try:
            collection_metadata = {"rr_data": rr_data.model_dump_json()}
            # NOTE: might want to remove collection_name from collection_metadata
            # since the user can rename the collection without updating the metadata
            ingest_docs_into_chroma_client(
                docs,
                collection_name=rr_data.collection_name,
                openai_api_key=chat_state.openai_api_key,
                chroma_client=chroma_client,
                collection_metadata=collection_metadata,
            )
            break  # success
        except Exception as e:  # bad name error may not be ValueError in docker mode
            if i or "Expected collection name" not in str(e):
                raise e  # i == 1 means tried normal name and random name, give up

            # Create a random valid collection name and try again
            rr_data.collection_name = construct_full_collection_name(
                chat_state.user_id,
                "collection-" + "".join(random.sample("abcdefghijklmnopqrstuvwxyz", 6)),
            )
    print("Done!")
    return response  # has answer, rr_data


NUM_NEW_OK_LINKS_TO_PROCESS = 2
INIT_BATCH_SIZE = 4


def prepare_next_iteration(chat_state: ChatState) -> dict[str, ParsedQuery]:
    research_params = chat_state.parsed_query.research_params
    if research_params.num_iterations_left < 2:
        return {}
    new_parsed_query = chat_state.parsed_query.model_copy()
    new_parsed_query.research_params.num_iterations_left -= 1
    new_parsed_query.message = None  # NOTE: need this?
    return {"new_parsed_query": new_parsed_query}


MAX_ITERATIONS_IF_COMMUNITY_KEY = 3
MAX_ITERATIONS_IF_OWN_KEY = 100


def get_iterative_researcher_response(chat_state: ChatState) -> Props:
    # Assign task type and get rr_data
    task_type = chat_state.parsed_query.research_params.task_type
    if task_type == ResearchCommand.NEW:
        return get_initial_iterative_researcher_response(chat_state)
    if task_type == ResearchCommand.AUTO:
        task_type = ResearchCommand.MORE  # we were routed here from main handler

    rr_data: ResearchReportData = chat_state.rr_data  # NOTE: might want to convert to
    # chat_state.get_rr_data() for readability

    if not rr_data or not rr_data.main_report:
        return format_invalid_input_answer(
            "Apologies, this command is only valid when there is an existing report.",
            "You can generate a new report using `/research new <query>`.",
        )

    # Fix for older style collections
    if not rr_data.base_reports:
        ok_links = [k for k, v in rr_data.link_data_dict.items() if not v.error]
        rr_data.base_reports.append(
            Report(
                report_text=rr_data.main_report,
                sources=ok_links[: -rr_data.num_obtained_unprocessed_ok_links],
                evaluation=rr_data.evaluation,
            )
        )

    # Validate number of iterations
    num_iterations_left = chat_state.parsed_query.research_params.num_iterations_left
    if chat_state.is_community_key:
        if num_iterations_left > MAX_ITERATIONS_IF_COMMUNITY_KEY:
            return format_invalid_input_answer(
                f"Apologies, a maximum of {MAX_ITERATIONS_IF_COMMUNITY_KEY} iterations is "
                "allowed when using a community OpenAI API key.",
                "Please try a lower number of iterations or use your OpenAI API key.",
            )
    else:
        if num_iterations_left > MAX_ITERATIONS_IF_OWN_KEY:
            return format_invalid_input_answer(
                f"For your protection, a maximum of {MAX_ITERATIONS_IF_OWN_KEY} iterations is "
                "allowed.",
                "Please try a lower number of iterations.",
            )

    t_start = datetime.now()
    print("Current version of report:\n", rr_data.main_report)
    print(DELIMITER)

    # Sanity check
    if (
        sum(
            1
            for link in rr_data.unprocessed_links[
                : rr_data.num_obtained_unprocessed_links
            ]
            if not rr_data.link_data_dict[link].error
        )
        != rr_data.num_obtained_unprocessed_ok_links
    ):
        raise ValueError("Mismatch in the number of obtained unprocessed good links")

    # Get content from more links if needed
    num_new_ok_links_to_process = (
        NUM_NEW_OK_LINKS_TO_PROCESS
        if task_type == ResearchCommand.ITERATE
        else NUM_OK_LINKS_NEW_REPORT  # "/research more"
    )
    num_ok_new_links_to_fetch = (
        num_new_ok_links_to_process - rr_data.num_obtained_unprocessed_ok_links
    )
    if num_ok_new_links_to_fetch > 0:
        link_data_dict = get_content_from_urls_with_top_up(
            rr_data.unprocessed_links[rr_data.num_obtained_unprocessed_links :],
            batch_fetcher=get_batch_fetcher(),
            min_ok_urls=num_ok_new_links_to_fetch,
            init_batch_size=INIT_BATCH_SIZE,
        )

        # Update rr_data
        rr_data.link_data_dict.update(link_data_dict)
        rr_data.num_obtained_unprocessed_links += len(link_data_dict)

        tmp = sum(1 for data in link_data_dict.values() if not data.error)
        rr_data.num_obtained_unprocessed_ok_links += tmp
        print()
    t_fetch_end = datetime.now()

    # Prepare links to include in the context (only good links)
    links_to_include = []
    links_to_count_tokens_for = []
    num_links_to_include = 0
    num_new_processed_links = 0
    for link in rr_data.unprocessed_links:
        # Stop if have enough links; consider only *obtained* links
        if (
            num_links_to_include == num_new_ok_links_to_process
            or num_new_processed_links == rr_data.num_obtained_unprocessed_links
        ):
            break
        num_new_processed_links += 1

        # Include link if it's good
        if rr_data.link_data_dict[link].error:
            continue
        links_to_include.append(link)
        num_links_to_include += 1

        # Check if we need to count tokens for this link
        if rr_data.link_data_dict[link].num_tokens is None:
            links_to_count_tokens_for.append(link)

    texts_to_include = [rr_data.link_data_dict[x].text for x in links_to_include]

    # Update rr_data once again to reflect the links about to be processed
    rr_data.processed_links += rr_data.unprocessed_links[:num_new_processed_links]
    rr_data.unprocessed_links = rr_data.unprocessed_links[num_new_processed_links:]
    rr_data.num_obtained_unprocessed_links -= num_new_processed_links
    rr_data.num_obtained_unprocessed_ok_links -= num_links_to_include

    # If no links to include, don't submit to LLM
    if not links_to_include:
        # Save new rr_data in chat_state (which saves it in the database) and return
        chat_state.save_rr_data(rr_data)
        return {
            "answer": "There are no more usable sources to incorporate into the report",
            "rr_data": rr_data,
            "needs_print": True,  # NOTE: this won't be streamed
        }

    # Count tokens in texts to be processed; throw in the report text too
    print("Counting tokens in texts and current report...")
    texts_to_count_tokens_for = [
        rr_data.link_data_dict[x].text for x in links_to_count_tokens_for
    ] + [rr_data.main_report]
    token_counts = get_num_tokens_in_texts(texts_to_count_tokens_for)

    num_tokens_report = token_counts[-1]
    for link, num_tokens in zip(links_to_count_tokens_for, token_counts):
        rr_data.link_data_dict[link].num_tokens = num_tokens

    # Shorten texts that are too long and construct combined sources text
    # TODO consider chunking and/or reducing num of included links instead
    print("Constructing final context...")
    final_texts, final_token_counts = limit_tokens_in_texts(
        texts_to_include,
        rr_data.max_tokens_final_context - num_tokens_report,
        cached_token_counts=[
            rr_data.link_data_dict[x].num_tokens for x in links_to_include
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

    # Assign the correct prompt and inputs
    print("Generating report...\n")
    if task_type == ResearchCommand.ITERATE:
        prompt = ITERATIVE_REPORT_IMPROVER_PROMPT
        inputs = {
            "new_info": final_context,
            "query": rr_data.query,
            "previous_report": rr_data.base_reports[-1].report_text,
        }
    else:
        prompt = RESEARCHER_PROMPT_INITIAL_REPORT
        inputs = {"texts_str": final_context, "query": rr_data.query}

    if "report_type" in prompt.input_variables:
        inputs["report_type"] = rr_data.report_type

    # Submit to LLM to generate report
    answer = get_prompt_llm_chain(
        prompt,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
        print_prompt=bool(os.getenv("PRINT_RESEARCHER_PROMPT")),
        callbacks=chat_state.callbacks,
        stream=True,
    ).invoke(inputs)

    # Extract and record the report and the LLM's assessment of the report
    report, evaluation = parse_iterative_report(answer)

    # Update rr_data
    if task_type == ResearchCommand.ITERATE:
        # Update the report that was just iteratively improved
        report_obj = Report(
            report_text=report,
            sources=rr_data.base_reports[-1].sources + links_to_include,
            evaluation=evaluation,
        )
        rr_data.base_reports[-1] = report_obj

        # Update the final report, if the "root" report is the one that was improved
        if len(rr_data.base_reports) == 1:
            rr_data.main_report = report
            rr_data.evaluation = evaluation

    else:  # "/research more"
        # Append the new report to the list of preliminary reports
        report_obj = Report(
            report_text=report, sources=links_to_include, evaluation=evaluation
        )
        rr_data.base_reports.append(report_obj)

    # Prepare new documents for ingestion
    # NOTE: links_to_include is non-empty if we got here
    print()  # we just printed the report, so add a newline
    print_no_newline("Ingesting new documents into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_include:
        link_data = rr_data.link_data_dict[link]
        metadata = {"source": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    ingest_docs_into_chroma_client(
        docs,
        collection_name=rr_data.collection_name,
        chroma_client=chat_state.vectorstore.client,
        openai_api_key=chat_state.openai_api_key,
    )

    # Save new rr_data in chat_state (which saves it in the database) and return
    chat_state.save_rr_data(rr_data)
    print("Done")
    return {
        "answer": answer,
        "rr_data": rr_data,
        "source_links": links_to_include,
    }  # NOTE: look into removing rr_data from the response


NUM_REPORTS_TO_COMBINE = 2
INVALID_COMBINE_MSG = (
    "Apologies, there are no reports in this collection that can be combined. "
    "You can start a new research using `/research <query>`. To "
    "generate more reports, so that you can combine them, use `/research more`."
)
INVALID_COMBINE_STATUS = "There are no reports in this collection that can be combined."


def get_report_combiner_response(chat_state: ChatState) -> Props:
    def get_ids_to_combine(id_list: list[str]) -> list[str] | None:
        # Check if there are enough uncombined reports at this level
        if len(id_list) < NUM_REPORTS_TO_COMBINE or not rr_data.is_report_childless(
            id_list[-NUM_REPORTS_TO_COMBINE]
        ):
            return None

        # Determine the earliest uncombined report at this level
        earliest_uncombined_idx = len(id_list) - NUM_REPORTS_TO_COMBINE
        while earliest_uncombined_idx:
            if rr_data.is_report_childless(id_list[earliest_uncombined_idx - 1]):
                earliest_uncombined_idx -= 1
            else:
                break

        # Determine ids of reports to combine
        return id_list[
            earliest_uncombined_idx : earliest_uncombined_idx + NUM_REPORTS_TO_COMBINE
        ]

    rr_data: ResearchReportData | None = chat_state.rr_data
    if not rr_data:
        return format_invalid_input_answer(INVALID_COMBINE_MSG, INVALID_COMBINE_STATUS)

    # See if there are enough uncombined reports at the highest level to combine them.
    # If not, go to the next level down, etc.
    depth = 0
    for i, id_list in enumerate(reversed(rr_data.combined_report_id_levels)):
        if ids_to_combine := get_ids_to_combine(id_list):
            depth = len(rr_data.combined_report_id_levels) - i
            break

    # If we didn't find enough higher level reports to combine, use base reports
    if depth == 0:
        id_list = [str(i) for i in range(len(rr_data.base_reports))]
        if not (ids_to_combine := get_ids_to_combine(id_list)):
            # If we still didn't find enough reports to combine, return
            return format_invalid_input_answer(
                INVALID_COMBINE_MSG, INVALID_COMBINE_STATUS
            )

    # Form input for the LLM
    inputs = {"query": rr_data.query}
    reports_to_combine = [rr_data.get_report_by_id(id) for id in ids_to_combine]
    for i, r in enumerate(reports_to_combine):
        # TODO: currently prompt doesn't support more than 2 reports
        inputs[f"report_{i+1}"] = r.report_text

    # Submit to LLM to generate combined report
    answer = get_prompt_llm_chain(
        REPORT_COMBINER_PROMPT,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
        print_prompt=bool(os.getenv("PRINT_RESEARCHER_PROMPT")),
        callbacks=chat_state.callbacks,
        stream=True,
    ).invoke(inputs)

    # Record the combined report and parent-child relationships
    new_id = f"c{len(rr_data.combined_reports)}"
    new_report = Report(report_text=answer, parent_report_ids=ids_to_combine)
    rr_data.combined_reports.append(new_report)
    for r in reports_to_combine:
        r.child_report_id = new_id

    # Record the combined report id at the correct level
    try:
        rr_data.combined_report_id_levels[depth].append(new_id)
    except IndexError:
        # Add a new level
        rr_data.combined_report_id_levels.append([new_id])

        # Also, in this case, update the main report
        rr_data.main_report = answer
        rr_data.evaluation = new_report.evaluation

    # Save new rr_data in chat_state (which saves it in the database) and return
    chat_state.save_rr_data(rr_data)
    sources = rr_data.get_sources(new_report)
    return {"answer": answer, "rr_data": rr_data, "source_links": sources}


def get_research_view_response(chat_state: ChatState) -> Props:
    def report_str_with_sources(report: Report) -> str:
        return f"{report.report_text}\n\nSOURCES:\n- " + "\n- ".join(
            rr_data.get_sources(report)
        )

    rr_data: ResearchReportData | None = chat_state.rr_data
    if not rr_data or not (num_reports := len(rr_data.base_reports)):
        return format_nonstreaming_answer(
            "There are no existing reports in this collection."
        )

    coll_name_as_shown = get_user_facing_collection_name(chat_state.vectorstore.name)
    answer = (
        f"Research result stats for collection `{coll_name_as_shown}`:\n"
        f"- There are {num_reports} base reports.\n"
        f"- There are {len(rr_data.combined_reports)} combined reports.\n"
        f"- There are {len(rr_data.processed_links)} processed links.\n"
        f"- There are {len(rr_data.unprocessed_links)} unprocessed links.\n"
        f"- Report levels breakdown: {[len(x) for x in rr_data.combined_report_id_levels]}"
    )

    sub_task = chat_state.parsed_query.research_params.sub_task
    if sub_task == "main":
        answer += f"\n\nMAIN REPORT:\n\n{rr_data.main_report}"
    elif sub_task == "base":
        answer += "\n\nBASE REPORTS:"
        for i, report in enumerate(rr_data.base_reports):
            answer += f"\n\n{i + 1}/{num_reports}:\n{report_str_with_sources(report)}"
    elif sub_task == "combined":
        answer += "\n\nCOMBINED REPORTS:"
        if not rr_data.combined_reports:
            answer += "\n\nThere are no combined reports."
        else:
            num_levels = len(rr_data.combined_report_id_levels)
            for i, id_list in enumerate(reversed(rr_data.combined_report_id_levels)):
                answer += f"\n\nLEVEL {num_levels - i}: {len(id_list)} REPORTS"
                for i, id in enumerate(id_list):
                    report = rr_data.get_report_by_id(id)
                    answer += f"\n\n{i + 1}/{len(id_list)}:\n{report_str_with_sources(report)}"
    else:
        raise ValueError(f"Invalid sub_task: {sub_task}")
    return format_nonstreaming_answer(answer)


def get_researcher_response_single_iter(chat_state: ChatState) -> Props:
    task_type = chat_state.parsed_query.research_params.task_type
    if task_type in {
        ResearchCommand.NEW,
        ResearchCommand.ITERATE,
        ResearchCommand.MORE,
    }:
        return get_iterative_researcher_response(chat_state)

    if task_type == ResearchCommand.COMBINE:
        return get_report_combiner_response(chat_state)

    if task_type == ResearchCommand.AUTO:
        response = get_report_combiner_response(chat_state)

        # If no error, return the response
        is_error = response.get("status.body") == INVALID_COMBINE_STATUS
        if not response.get("needs_print") and not is_error:
            return response

        # Sanity check
        assert is_error == bool(response.get("needs_print"))

        # We can't combine reports, so generate a new report instead
        return get_iterative_researcher_response(chat_state)

    if task_type == ResearchCommand.VIEW:
        return get_research_view_response(chat_state)

    if task_type == ResearchCommand.NONE:
        return format_nonstreaming_answer(RESEARCH_COMMAND_HELP_MESSAGE)

    raise ValueError(f"Invalid task type: {task_type}")


def get_researcher_response(chat_state: ChatState) -> Props:
    return get_researcher_response_single_iter(chat_state) | prepare_next_iteration(
        chat_state
    )  # contains parsed query for next iteration, if any


########### Snippet for contextual compression ############

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
