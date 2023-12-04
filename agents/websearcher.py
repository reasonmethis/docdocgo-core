from datetime import datetime
from enum import Enum
import json

from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from langchain.schema.output_parser import StrOutputParser
from utils.algo import remove_duplicates_keep_order
from utils.async_utils import gather_tasks_sync, make_sync
from utils.helpers import DELIMITER, print_no_newline
from utils.lang_utils import (
    get_max_token_allowance_for_texts,
    get_num_tokens,
    get_num_tokens_in_texts,
    limit_tokens_in_text,
    limit_tokens_in_texts,
)

from utils.prompts import (
    SIMPLE_WEBSEARCHER_PROMPT,
    QUERY_GENERATOR_PROMPT,
    SUMMARIZER_PROMPT,
    WEBSEARCHER_PROMPT_SIMPLE,
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


def add_links(current_links: list[str], new_links: list[str], num_links_to_add: int):
    num_added = 0
    for link in new_links:
        if num_added == num_links_to_add:
            return
        if link not in current_links and extract_domain(link) not in domain_blacklist:
            current_links.append(link)
            num_added += 1


def get_websearcher_response_quick(
    message: str, max_queries: int = 3, max_links_per_query: int = 3
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
    links = []
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    for search_result in search_results:
        links_for_query = [x["link"] for x in search_result["organic"]]
        add_links(links, links_for_query, max_links_per_query)
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


MAX_QUERY_GENERATOR_ATTEMPTS = 5


def get_websearcher_response_medium(
    query: str,
    max_queries: int = 7,
    max_links_per_query: int = 5,
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

    # Get links for each query by searching for it on Google
    print("Fetching search result links for each query...")
    num_queries = len(queries)
    ## if eg max_total_links=8 and num_queries=3, then we want 3, 3, 2 links per query
    max_links_per_query_final = max_total_links // num_queries
    max_links_per_query_init = max_links_per_query_final + 1
    threshold_idx = max_total_links % num_queries  # idx to switch from init to final
    ## do web searches for each query
    links = []
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    ## get links from search results
    for i, search_result in enumerate(search_results):
        num_links_to_add = min(
            max_links_per_query,
            max_links_per_query_init
            if i < threshold_idx
            else max_links_per_query_final,
        )
        links_for_query = [x["link"] for x in search_result["organic"]]
        add_links(links, links_for_query, num_links_to_add)
        # NOTE: can ask LLM to decide which links to keep
        # NOTE: can put the first link for each query at the top of the list, then 2nd, etc.

    print(f"Got {len(links)} links to research:\n- ", "\n- ".join(links), sep="")
    t_get_links_end = datetime.now()

    # Get content from links, measuring time taken
    print_no_newline("Fetching content from links...")
    htmls = make_sync(afetch_urls_in_parallel_playwright)(
        links, callback=lambda url, html: print_no_newline(".")
    )
    print()
    t_fetch_end = datetime.now()

    print_no_newline("Extracting main text from fetched content...")
    texts = [get_text_from_html(html) for html in htmls]
    print()
    # for text, html, link in zip(texts, htmls, links):
    #     print(DELIMITER)
    #     print(f"SOURCE: {link}")
    #     print("ALL TEXT:")
    #     print(get_text_from_html(html, mode="LC_BS_TRANSFORMER"))
    #     print(DELIMITER)
    #     print("MAIN TEXT:")
    #     print(text)
    #     input("Press Enter to continue...")
    # raise Exception("STOP")
    texts, links = remove_failed_fetches(texts, links)
    t_process_texts_end = datetime.now()

    # Summarize texts that are too long
    print("Counting tokens in texts...")
    max_tokens_per_text, token_counts = get_max_token_allowance_for_texts(
        texts, max_tokens_final_context
    )  # final context will include extra tokens for separators, links, etc.
    if False:  # skip for now
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

    print("Original number of links:", len(links))
    print("Number of links after removing unsuccessfully fetched ones:", len(links))
    print("Time taken to fetch sites:", t_fetch_end - t_get_links_end)
    print("Time taken to process html from sites:", t_process_texts_end - t_fetch_end)
    print(
        "Time taken to summarize/shorten texts:", t_summarize_end - t_process_texts_end
    )
    print("Number of resulting tokens:", get_num_tokens(final_context))

    print("Generating report...\n")
    chain = get_prompt_llm_chain(WEBSEARCHER_PROMPT_DYNAMIC_REPORT, stream=True)
    answer = chain.invoke(
        {"texts_str": final_context, "query": query, "report_type": report_type}
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
