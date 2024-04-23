from typing import Any

from langchain.utilities.google_serper import GoogleSerperAPIWrapper
from pydantic import BaseModel

from agentblocks.core import enforce_json_format
from components.llm import get_prompt_llm_chain
from utils.algo import interleave_iterables, remove_duplicates_keep_order
from utils.async_utils import gather_tasks_sync
from utils.chat_state import ChatState
from utils.type_utils import DDGError, Props

WEB_SEARCH_API_ISSUE_MSG = (
    "Apologies, it seems I'm having an issue with the API I use to search the web."
)

domain_blacklist = ["youtube.com"]


class WebSearchAPIError(DDGError):
    # NOTE: Can be raised e.g. like this: raise WebSearchAPIError() from e
    # In that case, the original exception will be stored in self.__cause__
    default_user_facing_message = WEB_SEARCH_API_ISSUE_MSG


def _extract_domain(url: str):
    try:
        full_domain = url.split("://")[-1].split("/")[0]  # blah.blah.domain.com
        return ".".join(full_domain.split(".")[-2:])  # domain.com
    except Exception:
        return ""


def _get_links(search_results: list[dict[str, Any]]):
    links_for_each_query = [
        [x["link"] for x in search_result.get("organic", []) if "link" in x]
        for search_result in search_results
    ]  # [[links for query 1], [links for query 2], ...]

    # NOTE: can ask LLM to decide which links to keep
    return [
        link
        for link in remove_duplicates_keep_order(
            interleave_iterables(links_for_each_query)
        )
        if _extract_domain(link) not in domain_blacklist
    ]


def get_links_from_queries(
    queries: list[str], num_search_results: int = 10
) -> list[str]:
    """
    Get links from a list of queries by doing a Google search for each query.
    """
    try:
        # Do a Google search for each query
        search = GoogleSerperAPIWrapper(k=num_search_results)
        search_tasks = [search.aresults(query) for query in queries]
        search_results = gather_tasks_sync(
            search_tasks
        )  # NOTE can use serper's batching

        # Get links from search results
        return _get_links(search_results)
    except Exception as e:
        raise WebSearchAPIError() from e


class Queries(BaseModel):
    queries: list[str]


def get_web_search_result_urls_from_prompt(
    prompt, inputs: Props, num_links, chat_state: ChatState
) -> list[str]:
    # Get queries to search for
    query_generator_chain = get_prompt_llm_chain(
        prompt,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
    )

    queries: list[str] = enforce_json_format(
        query_generator_chain,
        inputs=inputs,
        validator_transformer=Queries.model_validate_json,
    ).queries

    # Perform web search, get links
    return get_links_from_queries(queries, num_links)
