from datetime import datetime
from enum import Enum
import json

from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from langchain.schema.output_parser import StrOutputParser
from utils.async_utils import gather_tasks_sync, make_sync
from utils.helpers import DELIMITER
from utils.lang_utils import get_num_tokens, limit_tokens_in_texts

from utils.prompts import (
    SIMPLE_WEBSEARCHER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    SUMMARIZER_PROMPT,
    WEBSEARCHER_PROMPT,
    WEBSEARCHER_PROMPT_DYNAMIC_REPORT,
)
from utils.web import (
    get_text_from_html,
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

    chain = SIMPLE_WEBSEARCHER_PROMPT | get_llm(print_streamed=True) | StrOutputParser()
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


def filter_links(links: list[str], max_links: int):
    return [link for link in links if extract_domain(link) not in domain_blacklist][
        :max_links
    ]


def get_websearcher_response_quick(
    message: str, max_queries: int = 3, max_links_per_query: int = 3
):
    related_searches, people_also_ask = get_related_websearch_queries(message)

    # Get queries to search for
    queries = [message] + [
        query for query in related_searches + people_also_ask if query != message
    ]
    queries = queries[:max_queries]
    print("queries:", queries)

    # Get links
    links = []
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    for search_result in search_results:
        links_for_query = [x["link"] for x in search_result["organic"]]
        links += filter_links(links_for_query, max_links_per_query)
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

    processed_texts = limit_tokens_in_texts(ok_texts, max_tot_tokens=8000)
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

    chain = WEBSEARCHER_PROMPT | get_llm(print_streamed=True) | StrOutputParser()
    answer = chain.invoke({"texts_str": texts_str, "query": message})
    return {"answer": answer}


MAX_QUERY_GENERATOR_ATTEMPTS = 5


def get_websearcher_response_medium(
    query: str,
    max_queries: int = 7,
    max_links_per_query: int = 5,
    max_total_links: int = 20,
):
    # Get queries to search for using query generator prompt
    query_generator_chain = get_prompt_llm_chain(QUERY_GENERATOR_PROMPT)
    for i in range(MAX_QUERY_GENERATOR_ATTEMPTS):
        try:
            query_generator_output = query_generator_chain.invoke({"query": query})
            print("query_generator_output:", query_generator_output)
            query_generator_output = json.loads(query_generator_output)
            print("query_generator_output:", query_generator_output)
            queries = query_generator_output["queries"][:max_queries]
            print("queries:", queries)
            report_type = query_generator_output["report_type"]
            print("report_type:", report_type)
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

    # Get links for each query by searching on Google
    print("Fetching search result links for each query...")
    num_queries = len(queries)
    max_links_per_query_final = max_total_links // num_queries
    max_links_per_query_init = max_links_per_query_final + 1
    threshold_idx = max_total_links % num_queries
    links = []
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    for i, search_result in enumerate(search_results):
        num_links_per_query = min(
            max_links_per_query,
            max_links_per_query_init
            if i < threshold_idx
            else max_links_per_query_final,
        )
        links_for_query = [x["link"] for x in search_result["organic"]]
        links += filter_links(links_for_query, num_links_per_query)

    print(f"Got {len(links)} links to research:\n- ", "\n- ".join(links), sep="")
    t_get_links_end = datetime.now()

    # Get content from links, measuring time taken
    print("Fetching content from links...")
    htmls = make_sync(afetch_urls_in_parallel_playwright)(links)
    t_fetch_end = datetime.now()

    print("Extracting main text from fetched content...", end="", flush=True)
    texts = [get_text_from_html(html) for html in htmls]
    print()
    ok_texts, ok_links = remove_failed_fetches(texts, links)

    print("Combining texts and limiting the total number of tokens...")
    processed_texts = limit_tokens_in_texts(ok_texts, max_tot_tokens=8000)
    t_process_texts_end = datetime.now()

    # Summarize resulting texts
    print("Summarizing content...\n")
    summary_texts = []
    chain = (
        SUMMARIZER_PROMPT
        | get_llm(print_streamed=True, init_str="GENERATED SUMMARY: ")
        | StrOutputParser()
    )
    for text in processed_texts:
        summary_text = chain.invoke({"text": text, "query": query})
        summary_texts.append(summary_text)
        print(DELIMITER)
    t_summarize_end = datetime.now()

    processed_texts = [
        f"SOURCE: {link}\nCONTENT:\n{text}\n====="
        for text, link in zip(summary_texts, ok_links)
    ]
    texts_str = "\n\n".join(processed_texts)

    print("Original number of links:", len(links))
    print("Number of links after removing unsuccessfully fetched ones:", len(ok_links))
    print("Time taken to fetch sites:", t_fetch_end - t_get_links_end)
    print("Time taken to process html from sites:", t_process_texts_end - t_fetch_end)
    print("Time taken to summarize texts:", t_summarize_end - t_process_texts_end)
    print("Number of resulting tokens:", get_num_tokens(texts_str))

    print("Generating report...")
    chain = (
        WEBSEARCHER_PROMPT_DYNAMIC_REPORT
        | get_llm(print_streamed=True)
        | StrOutputParser()
    )
    answer = chain.invoke(
        {"texts_str": texts_str, "query": query, "report_type": report_type}
    )
    return {"answer": answer}


class WebsearcherMode(Enum):
    QUICK = 1
    MEDIUM = 2


def get_websearcher_response(message: str, mode=WebsearcherMode.MEDIUM):
    if mode == WebsearcherMode.QUICK:
        return get_websearcher_response_quick(message)
    elif mode == WebsearcherMode.MEDIUM:
        return get_websearcher_response_medium(message)
    raise ValueError(f"Invalid mode: {mode}")
