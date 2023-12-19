import json
from datetime import datetime
from enum import Enum
from typing import Any

from chromadb import API
from langchain.schema import Document
from langchain.schema.output_parser import StrOutputParser
from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from pydantic import BaseModel

from components.llm import get_llm, get_prompt_llm_chain
from utils.algo import interleave_iterables, remove_duplicates_keep_order
from utils.async_utils import gather_tasks_sync, make_sync
from utils.docgrab import ingest_docs_into_chroma_client
from utils.helpers import DELIMITER, print_no_newline
from utils.lang_utils import (
    get_max_token_allowance_for_texts,
    get_num_tokens,
    get_num_tokens_in_texts,
    limit_tokens_in_text,
    limit_tokens_in_texts,
)
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import (
    ITERATIVE_REPORT_IMPROVER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    SIMPLE_WEBSEARCHER_PROMPT,
    SUMMARIZER_PROMPT,
    WEBSEARCHER_PROMPT_DYNAMIC_REPORT,
    WEBSEARCHER_PROMPT_SIMPLE,
)
from utils.type_utils import ChatState
from utils.web import (
    afetch_urls_in_parallel_aiohttp,
    afetch_urls_in_parallel_playwright,
    get_text_from_html,
    is_html_text_ok,
    remove_failed_fetches,
)
import secrets

search = GoogleSerperAPIWrapper()

def get_related_websearch_queries(message: str):
    search_results = search.results(message)
    # print("search results:", json.dumps(search_results, indent=4))
    related_searches = [x["query"] for x in search_results.get("relatedSearches", [])]
    people_also_ask = [x["question"] for x in search_results.get("peopleAlsoAsk", [])]

    return related_searches, people_also_ask


def extract_domain(url: str):
    try:
        full_domain = url.split("://")[-1].split("/")[0]  # blah.blah.domain.com
        return ".".join(full_domain.split(".")[-2:])  # domain.com
    except Exception:
        return ""


domain_blacklist = ["youtube.com"]


def get_links(search_results: list[dict[str, Any]]):
    # current_links: list[str], new_links: list[str], num_links_to_add: int):
    links_for_each_query = [
        [x["link"] for x in search_result["organic"]]
        for search_result in search_results
    ]  # [[links for query 1], [links for query 2], ...]

    # NOTE: can ask LLM to decide which links to keep
    return [
        link
        for link in remove_duplicates_keep_order(
            interleave_iterables(links_for_each_query)
        )
        if extract_domain(link) not in domain_blacklist
    ]

def get_websearcher_response_quick(
    chat_state: ChatState, max_queries: int = 3, max_total_links: int = 9
):
    """
    Perform quick web research on a query, with only one call to the LLM.

    It gets related queries to search for by examining the "related searches" and
    "people also ask" sections of the Google search results for the query. It then
    searches for each of these queries on Google, and gets the top links for each
    query. It then fetches the content from each link, shortens them to fit all
    texts into one context window, and then sends it to the LLM to generate a report.
    """
    message = chat_state.message
    related_searches, people_also_ask = get_related_websearch_queries(message)

    # Get queries to search for
    queries = [message] + [
        query for query in related_searches + people_also_ask if query != message
    ]
    queries = queries[:max_queries]
    print("queries:", queries)

    # Get links
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    links = get_links(search_results)[:max_total_links]
    print("links:", links)

    # Get content from links, measuring time taken
    t_start = datetime.now()
    print("Fetching content from links...")
    # htmls = make_sync(afetch_urls_in_parallel_chromium_loader)(links)
    htmls = make_sync(afetch_urls_in_parallel_playwright)(links)
    # htmls = make_sync(afetch_urls_in_parallel_html_loader)(links)
    # htmls = fetch_urls_with_lc_html_loader(links) # takes ~20s, slow
    t_fetch_end = datetime.now()

    print("Processing content...")
    texts = [get_text_from_html(html) for html in htmls]
    ok_texts, ok_links = remove_failed_fetches(texts, links)

    processed_texts, token_counts = limit_tokens_in_texts(
        ok_texts, max_tot_tokens=int(CONTEXT_LENGTH * 0.5)
    )
    processed_texts = [
        f"SOURCE: {link}\nCONTENT:\n{text}\n====="
        for text, link in zip(processed_texts, ok_links)
    ]
    texts_str = "\n\n".join(processed_texts)
    t_end = datetime.now()

    print("CONTEXT FOR GENERATING REPORT:\n")
    print(texts_str + "\n" + "=" * 100 + "\n")
    print("Original number of links:", len(links))
    print("Number of links after removing unsuccessfully fetched ones:", len(ok_links))
    print("Time taken to fetch sites:", t_fetch_end - t_start)
    print("Time taken to process sites:", t_end - t_fetch_end)
    print("Number of resulting tokens:", get_num_tokens(texts_str))

    chain = get_prompt_llm_chain(
        WEBSEARCHER_PROMPT_SIMPLE, callbacks=chat_state.callbacks, stream=True
    )
    answer = chain.invoke({"texts_str": texts_str, "query": message})
    return {"answer": answer}


class LinkData(BaseModel):
    text: str | None = None
    error: str | None = None
    num_tokens: int | None = None

    @classmethod
    def from_html(cls, html: str):
        if html.startswith("Error: "):
            return cls(error=html)
        text = get_text_from_html(html)
        if is_html_text_ok(text):
            return cls(text=text)
        return cls(text=text, error="UNACCEPTABLE_EXTRACTED_TEXT")


class WebsearcherData(BaseModel):
    query: str
    report: str
    report_type: str
    unprocessed_links: list[str]
    processed_links: list[str]
    link_data_dict: dict[str, LinkData]
    evaluation: str | None = None
    collection_name: str | None = None
    max_tokens_final_context: int = int(CONTEXT_LENGTH * 0.7)

    @classmethod
    def from_query(cls, query: str):
        return cls(
            query=query,
            report="",
            report_type="",
            unprocessed_links=[],
            processed_links=[],
            link_data_dict={},
        )


MAX_QUERY_GENERATOR_ATTEMPTS = 5


def get_websearcher_response_medium(    
    chat_state: ChatState,
    max_queries: int = 7,
    max_total_links: int = 7,  # TODO! # small number to stuff into context window
    max_tokens_final_context: int = int(CONTEXT_LENGTH * 0.7),
):
    query = chat_state.message
    # Get queries to search for using query generator prompt
    query_generator_chain = get_prompt_llm_chain(QUERY_GENERATOR_PROMPT)
    for i in range(MAX_QUERY_GENERATOR_ATTEMPTS):
        try:
            query_generator_output = query_generator_chain.invoke(
                {
                    "query": query,
                    "timestamp": datetime.now().strftime("%A, %B %d, %Y, %I:%M %p"),
                    # "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
            )
            print("query_generator_output:", query_generator_output)
            query_generator_output = json.loads(query_generator_output.strip())
            queries = query_generator_output["queries"][:max_queries]
            report_type = query_generator_output["report_type"]
            break
        except Exception as err_local:
            print(
                f"Failed to generate queries on attempt {i+1}/{MAX_QUERY_GENERATOR_ATTEMPTS}. "
                f"Error: \n{err_local}"
            )
            e = err_local
    else:
        raise Exception(f'Failed to generate queries for query: "{query}".\nError: {e}')

    print("Generated queries:", repr(queries).strip("[]"))
    print("Report type will be:", repr(report_type))

    try:
        # Do a Google search for each query
        print("Fetching search result links for each query...")
        links = []
        search_tasks = [search.aresults(query) for query in queries]
        search_results = gather_tasks_sync(search_tasks)

        # Get links from search results
        all_links = get_links(search_results)
        links = all_links[:max_total_links]  # links we will process in this run
        print(f"Got {len(links)} links to research:\n- ", "\n- ".join(links), sep="")
        t_get_links_end = datetime.now()
    except Exception as e:
        raise ValueError(f"Failed to get links: {e}")

    try:
        # Get content from links
        print_no_newline("Fetching content from links...")
        import os
        htmls = make_sync(afetch_urls_in_parallel_playwright)(
            links, callback=lambda url, html: print_no_newline(".")
        ) if os.getenv("USE_PLAYWRIGHT") else make_sync(afetch_urls_in_parallel_aiohttp)(
            links
        )
        print()
        t_fetch_end = datetime.now()
    except Exception as e:
        raise ValueError(f"Failed to get htmls: {e}, links: {links}")

    try:
        # Initialize data object
        ws_data = WebsearcherData.from_query(query)
        ws_data.report_type = report_type
        ws_data.processed_links = links  # we will process these links in this function
        ws_data.unprocessed_links = all_links[max_total_links:]

        # Get text from html
        print_no_newline("Extracting main text from fetched content...")
        for link, html in zip(links, htmls):
            ws_data.link_data_dict[link] = LinkData.from_html(html)
            print_no_newline(".")
        print()

        # Get a list of acceptably fetched links and their texts
        links = [link for link in links if ws_data.link_data_dict[link].error is None]
        texts = [ws_data.link_data_dict[link].text for link in links]
        t_process_texts_end = datetime.now()

        token_counts = None  # to make limit_tokens_in_texts() work either way
    except Exception as e:
        htmls_str = '\n\n'.join(x[:200] for x in htmls)
        raise ValueError(f"Failed to get texts: {e}, htmls:\n{htmls_str}")

    try:
        print("Constructing final context...")
        final_texts, final_token_counts = limit_tokens_in_texts(
            texts, max_tokens_final_context, cached_token_counts=token_counts
        )
        final_texts = [
            f"SOURCE: {link}\nCONTENT:\n{text}\n====="
            for text, link in zip(final_texts, links)
        ]
        final_context = "\n\n".join(final_texts)
        t_summarize_end = datetime.now()

        print(
            "Number of obtained links:",
            len(ws_data.processed_links) + len(ws_data.unprocessed_links),
        )
        print("Number of processed links:", len(ws_data.processed_links))
        print("Number of links after removing unsuccessfully fetched ones:", len(links))
        print("Time taken to fetch sites:", t_fetch_end - t_get_links_end)
        print("Time taken to process html from sites:", t_process_texts_end - t_fetch_end)
        print(
            "Time taken to summarize/shorten texts:", t_summarize_end - t_process_texts_end
        )
        print("Number of resulting tokens:", get_num_tokens(final_context))

        print("Generating report...\n")
        chain = get_prompt_llm_chain(
            WEBSEARCHER_PROMPT_DYNAMIC_REPORT, callbacks=chat_state.callbacks, stream=True
        )
        ws_data.report = chain.invoke(
            {"texts_str": final_context, "query": query, "report_type": report_type}
        )
        return {
            "answer": ws_data.report,
            "ws_data": ws_data,
        }
    except Exception as e:
        final_texts_str = '\n\n'.join(x[:200] for x in final_texts)
        raise ValueError(f"Failed to get report: {e}, final_texts: {final_texts_str}")


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


NUM_NEW_LINKS_TO_ACQUIRE = 3
NUM_NEW_LINKS_TO_PROCESS = 2

SMALL_WORDS = {"a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or"}
SMALL_WORDS |= {"is", "are", "was", "were", "be", "been", "being", "am", "what"}
SMALL_WORDS |= {"which", "who", "whom", "whose", "where", "when", "how", "why"}


def get_initial_iterative_researcher_response(
    chat_state: ChatState,
) -> WebsearcherData:
    ws_data = get_websearcher_response_medium(chat_state)["ws_data"]
    answer = ws_data.report  # TODO consider including report in the db

    # Determine which links to include in the db
    links_to_include = [
        link for link, data in ws_data.link_data_dict.items() if not data.error
    ]
    if not links_to_include:
        return ws_data

    # Decide on the collection name consistent with ChromaDB's naming rules
    query_words = ws_data.query.split()
    words = [x.lower() for x in query_words if x not in SMALL_WORDS]
    if len(words) < 3:
        words = [x.lower() for x in query_words]
    new_coll_name = "-".join(words[:3])
    new_coll_name = "".join(x for x in new_coll_name if x.isalnum() or x == "-")
    new_coll_name = new_coll_name.lstrip("-")[:35].rstrip("-")
    if len(new_coll_name) < 3:
        new_coll_name = f"collection-{new_coll_name}".rstrip("-")
    ws_data.collection_name = new_coll_name

    # Check if collection exists, if so, add a number to the end
    chroma_client: API = chat_state.vectorstore._client
    for i in range(2, 1000000):
        try:
            chroma_client.get_collection(ws_data.collection_name)
        except ValueError:
            break  # collection does not exist
        ws_data.collection_name = f"{new_coll_name}-{i}"

    # Convert website content into documents for ingestion
    print("Ingesting fetched content into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_include:
        link_data = ws_data.link_data_dict[link]
        metadata = {"url": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    try:
        ingest_docs_into_chroma_client(docs, ws_data.collection_name, chroma_client)
    except ValueError:
        # Catching ValueError: Expected collection name ...
        # Create a random valid collection name and try again
        ws_data.collection_name = "collection-" + "".join(
            secrets.SystemRandom().sample("abcdefghijklmnopqrstuvwxyz", 6)
        )
        ingest_docs_into_chroma_client(docs, ws_data.collection_name, chroma_client)
    return {"answer": answer, "ws_data": ws_data}


def get_iterative_researcher_response(
    chat_state: ChatState,
) -> WebsearcherData:
    ws_data: WebsearcherData = chat_state.ws_data

    # Special handling for first iteration
    if not ws_data.report:
        return get_initial_iterative_researcher_response(chat_state)

    t_start = datetime.now()
    links_to_get = ws_data.unprocessed_links[:NUM_NEW_LINKS_TO_ACQUIRE]

    # Some links may have already been fetched (but not processed)
    links_to_fetch = [
        link for link in links_to_get if link not in ws_data.link_data_dict
    ]

    # Get content from links
    print_no_newline(f"{len(links_to_fetch)} links to fetch content from")
    if links_to_fetch:
        print(":\n- " + "\n- ".join(links_to_fetch))
        print_no_newline("Fetching content from links...")
        htmls = make_sync(afetch_urls_in_parallel_playwright)(
            links_to_fetch, callback=lambda url, html: print_no_newline(".")
        )
        print()
    t_fetch_end = datetime.now()

    # Get text from html
    if links_to_fetch:
        print_no_newline("Extracting main text from fetched content...")
        for link, html in zip(links_to_fetch, htmls):
            ws_data.link_data_dict[link] = LinkData.from_html(html)
            print_no_newline(".")
        print()
    t_extract_texts_end = datetime.now()

    # Links to process (already fetched)
    # TODO tmp = [link for link in links_to_get if not ws_data.link_data_dict[link].error]
    links_to_process = links_to_get[:NUM_NEW_LINKS_TO_PROCESS]
    links_to_include = [
        x for x in links_to_process if not ws_data.link_data_dict[x].error
    ]
    texts_to_include = [ws_data.link_data_dict[x].text for x in links_to_include]

    # Count tokens in texts to be processed; throw in the report text too
    print("Counting tokens in texts and current report...")
    links_to_count_tokens_for = [
        x for x in links_to_include if ws_data.link_data_dict[x].num_tokens is None
    ]
    texts_to_count_tokens_for = [
        ws_data.link_data_dict[x].text for x in links_to_count_tokens_for
    ] + [ws_data.report]
    token_counts = get_num_tokens_in_texts(texts_to_count_tokens_for)

    num_tokens_report = token_counts[-1]
    for link, num_tokens in zip(links_to_count_tokens_for, token_counts):
        ws_data.link_data_dict[link].num_tokens = num_tokens

    # Shorten texts that are too long and construct combined sources text
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
    ]
    final_context = "\n\n".join(final_texts)
    t_construct_context_end = datetime.now()

    print("Time taken to fetch sites:", t_fetch_end - t_start)
    print("Time taken to process html from sites:", t_extract_texts_end - t_fetch_end)
    print("Time taken to process texts:", t_construct_context_end - t_extract_texts_end)
    num_tokens_final_context = get_num_tokens(final_context)
    print("Number of resulting tokens in the context:", num_tokens_final_context)
    print(
        "Number of resulting tokens in the context + report:",
        num_tokens_report + num_tokens_final_context,
    )

    print("Generating report...\n")
    chain = get_prompt_llm_chain(
        ITERATIVE_REPORT_IMPROVER_PROMPT, callbacks=chat_state.callbacks, stream=True
    )
    answer = chain.invoke(
        {
            "new_info": final_context,
            "query": ws_data.query,
            "previous_report": ws_data.report,
        }
    )

    # Extract and record treport and the LLM's assessment of the report
    REPORT_ASSESSMENT_MSG = "REPORT ASSESSMENT:"
    NO_IMPROVEMENT_MSG = "NO IMPROVEMENT, PREVIOUS REPORT ASSESSMENT:"
    length_diff = len(NO_IMPROVEMENT_MSG) - len(REPORT_ASSESSMENT_MSG)

    idx_assessment = answer.rfind(REPORT_ASSESSMENT_MSG)
    if idx_assessment == -1:
        # Something went wrong, keep the old report
        print("Something went wrong, keeping the old report")  # NOTE: can remove
    else:
        idx_no_improvement = idx_assessment - length_diff
        if (
            idx_no_improvement >= 0
            and answer[
                idx_no_improvement : idx_no_improvement + len(NO_IMPROVEMENT_MSG)
            ]
            == NO_IMPROVEMENT_MSG
        ):
            # No improvement, keep the old report, record the LLM's assessment
            print("No improvement, keeping the old report")  # NOTE: can remove
            ws_data.evaluation = answer[idx_no_improvement:]
        else:
            # Improvement, record the new report and the LLM's assessment
            ws_data.report = answer
            ws_data.evaluation = answer[idx_assessment:]

    ws_data.processed_links += links_to_process
    ws_data.unprocessed_links = ws_data.unprocessed_links[len(links_to_process) :]

    if links_to_include:
        # Prepare new documents for ingestion
        print("Ingesting new documents into ChromaDB...")
        docs: list[Document] = []
        for link in links_to_include:
            link_data = ws_data.link_data_dict[link]
            metadata = {"url": link}
            if link_data.num_tokens is not None:
                metadata["num_tokens"] = link_data.num_tokens
            docs.append(Document(page_content=link_data.text, metadata=metadata))

        # Ingest documents into ChromaDB
        ingest_docs_into_chroma_client(
            docs, ws_data.collection_name, chat_state.vectorstore._client
        )

    return {"answer": answer, "ws_data": ws_data}


class WebsearcherMode(Enum):
    QUICK = 1
    MEDIUM = 2
    TEST=3

def get_websearcher_response(chat_state: ChatState, mode=WebsearcherMode.MEDIUM):
    if mode == WebsearcherMode.QUICK:
        return get_websearcher_response_quick(chat_state)
    elif mode == WebsearcherMode.MEDIUM:
        return get_websearcher_response_medium(chat_state)
    elif mode == WebsearcherMode.TEST:
        return get_websearcher_response_medium(chat_state)
        # return get_web_test_response(chat_state)
    raise ValueError(f"Invalid mode: {mode}")
