from datetime import datetime
import json

from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from langchain.schema.output_parser import StrOutputParser
from utils.async_utils import gather_tasks_sync, make_sync
from utils.lang_utils import get_num_tokens, limit_tokens_in_texts

from utils.prompts import SIMPLE_WEBSEARCHER_PROMPT, WEBSEARCHER_PROMPT
from utils.web import (
    get_text_from_html,
    remove_failed_fetches,
    afetch_urls_in_parallel_html_loader,
    afetch_urls_in_parallel_chromium_loader,
    afetch_urls_in_parallel_playwright,
)
from components.llm import get_llm

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


def get_websearcher_response(
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
    print("Fetching content from links...")
    # htmls = make_sync(afetch_urls_in_parallel_chromium_loader)(links)
    htmls = make_sync(afetch_urls_in_parallel_playwright)(links)
    # htmls = make_sync(afetch_urls_in_parallel_html_loader)(links)
    # htmls = fetch_urls_with_lc_html_loader(links) # takes ~20s, slow

    t_start = datetime.now()
    print("Processing content...")
    texts = [get_text_from_html(html) for html in htmls]
    ok_texts, ok_links = remove_failed_fetches(texts, links)

    processed_texts = limit_tokens_in_texts(ok_texts, max_tot_tokens=8000)
    t_end = datetime.now()
    processed_texts = [
        f"SOURCE: {link}\nCONTENT:\n{text}\n====="
        for text, link in zip(processed_texts, ok_links)
    ]
    texts_str = "\n\n".join(processed_texts)

    print("CONTEXT FOR GENERATING REPORT:\n")
    print(texts_str + "\n" + "=" * 100 + "\n")
    print("Original number of links:", len(links))
    print("Number of links after removing unsuccessfully fetched ones:", len(ok_links))
    print("Time taken:", t_end - t_start)
    print("Number of resulting tokens:", get_num_tokens(texts_str))

    chain = WEBSEARCHER_PROMPT | get_llm(print_streamed=True) | StrOutputParser()
    answer = chain.invoke({"texts_str": texts_str, "query": message})
    return {"answer": answer}
