from datetime import datetime

from agentblocks.websearch import get_links_from_search_results
from components.llm import get_prompt_llm_chain
from utils.async_utils import gather_tasks_sync, make_sync
from utils.chat_state import ChatState
from utils.lang_utils import get_num_tokens, limit_tokens_in_texts
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import RESEARCHER_PROMPT_SIMPLE
from utils.web import (
    afetch_urls_in_parallel_playwright,
    get_text_from_html,
    remove_failed_fetches,
)
from langchain_community.utilities import GoogleSerperAPIWrapper


def get_related_websearch_queries(message: str):
    search = GoogleSerperAPIWrapper()
    search_results = search.results(message)
    # print("search results:", json.dumps(search_results, indent=4))
    related_searches = [x["query"] for x in search_results.get("relatedSearches", [])]
    people_also_ask = [x["question"] for x in search_results.get("peopleAlsoAsk", [])]

    return related_searches, people_also_ask


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
    search = GoogleSerperAPIWrapper()
    search_tasks = [search.aresults(query) for query in queries]
    search_results = gather_tasks_sync(search_tasks)
    links = get_links_from_search_results(search_results)[:max_total_links]
    print("Links:", links)

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
        RESEARCHER_PROMPT_SIMPLE,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
        callbacks=chat_state.callbacks,
        stream=True,
    )
    answer = chain.invoke({"texts_str": texts_str, "query": message})
    return {"answer": answer}
