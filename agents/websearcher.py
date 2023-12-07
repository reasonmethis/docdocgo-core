from typing import Any
from datetime import datetime
from enum import Enum
import json

from pydantic import BaseModel
from chromadb import ClientAPI
from langchain.schema import Document
from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from langchain.schema.output_parser import StrOutputParser
from components.chroma_ddg import ChromaDDG

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

from utils.prompts import (
    ITERATIVE_REPORT_IMPROVER_PROMPT,
    SIMPLE_WEBSEARCHER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    SUMMARIZER_PROMPT,
    WEBSEARCHER_PROMPT_SIMPLE,
    WEBSEARCHER_PROMPT_DYNAMIC_REPORT,
)
from utils.web import (
    get_text_from_html,
    is_html_text_ok,
    remove_failed_fetches,
    afetch_urls_in_parallel_html_loader,
    afetch_urls_in_parallel_chromium_loader,
    afetch_urls_in_parallel_playwright,
)
from components.llm import get_llm, get_prompt_llm_chain

search = GoogleSerperAPIWrapper()


def get_simple_websearcher_response(message: str):
    search_results = search.results(message)
    json_results = json.dumps(search_results, indent=4)
    # print(json_results)

    chain = SIMPLE_WEBSEARCHER_PROMPT | get_llm(stream=True) | StrOutputParser()
    answer = chain.invoke({"results": json_results, "query": message})
    return {"answer": answer}


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
    except:
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
    message: str, max_queries: int = 3, max_total_links: int = 9
):
    """
    Perform quick web research on a query, with only one call to the LLM.

    It gets related queries to search for by examining the "related searches" and
    "people also ask" sections of the Google search results for the query. It then
    searches for each of these queries on Google, and gets the top links for each
    query. It then fetches the content from each link, shortens them to fit all
    texts into one context window, and then sends it to the LLM to generate a report.
    """
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

    processed_texts, token_counts = limit_tokens_in_texts(ok_texts, max_tot_tokens=8000)
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

    chain = WEBSEARCHER_PROMPT_SIMPLE | get_llm(stream=True) | StrOutputParser()
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
    max_tokens_final_context: int = 8000

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
    query: str,
    max_queries: int = 7,
    max_total_links: int = 7,  # small number to stuff into context window
    max_tokens_final_context: int = 8000,
):
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
            query_generator_output = json.loads(query_generator_output)
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

    # Get content from links
    print_no_newline("Fetching content from links...")
    htmls = make_sync(afetch_urls_in_parallel_playwright)(
        links, callback=lambda url, html: print_no_newline(".")
    )
    print()
    t_fetch_end = datetime.now()

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

    if False:  # skip contextual compression (loses info, at least with GPT-3.5)
        print("Counting tokens in texts...")
        max_tokens_per_text, token_counts = get_max_token_allowance_for_texts(
            texts, max_tokens_final_context
        )  # final context will include extra tokens for separators, links, etc.

        print(
            f"Removing irrelevant parts from texts that have over {max_tokens_per_text} tokens..."
        )
        new_texts = []
        new_token_counts = []
        for text, link, num_tokens in zip(texts, links, token_counts):
            if num_tokens <= max_tokens_per_text:
                # Don't summarize short texts
                print("KEEPING:", link, "(", num_tokens, "tokens )")
                new_texts.append(text)
                new_token_counts.append(num_tokens)
                continue
            # If it's way too long, first just shorten it mechanically
            # NOTE: can instead chunk it
            if num_tokens > max_tokens_final_context:
                text = limit_tokens_in_text(
                    text, max_tokens_final_context, slow_down_factor=0
                )
            print("SHORTENING:", link)
            print("CONTENT:", text)
            print(DELIMITER)
            chain = get_prompt_llm_chain(
                SUMMARIZER_PROMPT, init_str=f"SHORTENED TEXT FROM {link}: ", stream=True
            )
            try:
                new_text = chain.invoke({"text": text, "query": query})
            except Exception as e:
                new_text = "<ERROR WHILE GENERATING CONTENT>"
            num_tokens = get_num_tokens(new_text)
            new_texts.append(new_text)
            new_token_counts.append(num_tokens)
            print(DELIMITER)
        texts, token_counts = new_texts, new_token_counts
    else:
        token_counts = None  # to make limit_tokens_in_texts() work either way

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
    chain = get_prompt_llm_chain(WEBSEARCHER_PROMPT_DYNAMIC_REPORT, stream=True)
    ws_data.report = chain.invoke(
        {"texts_str": final_context, "query": query, "report_type": report_type}
    )
    return {
        "answer": ws_data.report,
        "ws_data": ws_data,
    }


NUM_NEW_LINKS_TO_ACQUIRE = 3
NUM_NEW_LINKS_TO_PROCESS = 2

SMALL_WORDS = {"a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or"}


def get_initial_iterative_researcher_response(
    ws_data: WebsearcherData,
    chroma_client: ClientAPI,
) -> WebsearcherData:
    ws_data = get_websearcher_response_medium(ws_data.query)["ws_data"]

    # Decide on the collection name
    query_words = ws_data.query.split()
    words = [x.lower() for x in query_words if x not in SMALL_WORDS]
    if len(words) < 2:
        words = [x.lower() for x in query_words]
    ws_data.collection_name = orig_name = "-".join(words[:3])[:60].rstrip("-")

    # Check if collection exists, if so, add a number to the end
    for i in range(1, 1000000000):
        try:
            chroma_client.get_collection(ws_data.collection_name)
        except ValueError:
            break  # collection does not exist
        ws_data.collection_name = f"{orig_name}-{i}"

    # Convert website content into documents for ingestion
    print("Ingesting fetched content into ChromaDB...")
    docs: list[Document] = []
    for link, link_data in ws_data.link_data_dict.items():
        if link_data.error:
            continue
        metadata = {"url": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    vectorstore = ingest_docs_into_chroma_client(
        docs, ws_data.collection_name, chroma_client
    )
    return ws_data


def get_iterative_researcher_response(
    ws_data: WebsearcherData,
    vectorstore: ChromaDDG,
) -> WebsearcherData:
    # Special handling for first iteration
    if not ws_data.report:
        return get_initial_iterative_researcher_response(ws_data, vectorstore._client)

    t_start = datetime.now()
    links_to_get = ws_data.unprocessed_links[:NUM_NEW_LINKS_TO_ACQUIRE]

    # Some links may have already been fetched (but not processed)
    links_to_fetch = [
        link for link in links_to_get if link not in ws_data.link_data_dict
    ]

    # Get content from links
    print_no_newline(f"{len(links_to_fetch)} links to fetch content from")
    if links_to_fetch:
        print(f":\n- ", "\n- ".join(links_to_fetch), sep="")
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
    links_to_process = ws_data.unprocessed_links[:NUM_NEW_LINKS_TO_PROCESS]
    texts_to_process = [ws_data.link_data_dict[link].text for link in links_to_process]

    # Count tokens in texts to be processed; throw in the report text too
    print("Counting tokens in texts and current report...")
    links_to_count_tokens_for = [
        x for x in links_to_process if ws_data.link_data_dict[x].num_tokens is None
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
        texts_to_process,
        ws_data.max_tokens_final_context - num_tokens_report,
        cached_token_counts=[
            ws_data.link_data_dict[x].num_tokens for x in links_to_process
        ],
    )
    final_texts = [
        f"SOURCE: {link}\nCONTENT:\n{text}\n====="
        for text, link in zip(final_texts, links_to_process)
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
    chain = get_prompt_llm_chain(ITERATIVE_REPORT_IMPROVER_PROMPT, stream=True)
    answer = chain.invoke(
        {
            "new_info": final_context,
            "query": ws_data.query,
            "previous_report": ws_data.report,
        }
    )

    # TODO update this
    if "NO_IMPROVEMENT" in answer:
        ws_data.evaluation = answer
    else:
        ws_data.report = answer
    ws_data.unprocessed_links = ws_data.unprocessed_links[NUM_NEW_LINKS_TO_PROCESS:]
    ws_data.processed_links += links_to_process

    # Prepare new documents for ingestion
    print("Ingesting new documents into ChromaDB...")
    docs: list[Document] = []
    for link in links_to_process:
        link_data = ws_data.link_data_dict[link]
        if link_data.error:
            continue
        metadata = {"url": link}
        if link_data.num_tokens is not None:
            metadata["num_tokens"] = link_data.num_tokens
        docs.append(Document(page_content=link_data.text, metadata=metadata))

    # Ingest documents into ChromaDB
    ingest_docs_into_chroma_client(docs, ws_data.collection_name, vectorstore._client)

    return ws_data


class WebsearcherMode(Enum):
    QUICK = 1
    MEDIUM = 2
    ITERATIVE = 3


def get_websearcher_response(message: str, mode=WebsearcherMode.MEDIUM):
    if mode == WebsearcherMode.QUICK:
        return get_websearcher_response_quick(message)
    elif mode == WebsearcherMode.MEDIUM:
        return get_websearcher_response_medium(message)
    raise ValueError(f"Invalid mode: {mode}")
