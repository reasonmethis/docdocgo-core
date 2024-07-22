from typing import Any
from pydantic import BaseModel

from agentblocks.core import enforce_pydantic_json
from utils.algo import interleave_iterables, remove_duplicates_keep_order
from utils.async_utils import gather_tasks_sync
from utils.chat_state import ChatState
from utils.prepare import get_logger
from utils.type_utils import DDGError
from langchain_community.utilities import GoogleSerperAPIWrapper

logger = get_logger()

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


def get_links_from_search_results(search_results: list[dict[str, Any]]):
    logger.debug(
        f"Getting links from results of {len(search_results)} searches "
        f"with {[len(s) for s in search_results]} links each."
    )
    links_for_each_query = [
        [x["link"] for x in search_result.get("organic", []) if "link" in x]
        for search_result in search_results
    ]  # [[links for query 1], [links for query 2], ...]

    logger.debug(
        f"Number of links for each query: {[len(links) for links in links_for_each_query]}"
    )
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
        logger.info(f"Performing web search for queries: {queries}")
        search = GoogleSerperAPIWrapper(k=num_search_results)
        search_tasks = [search.aresults(query) for query in queries]
        search_results = gather_tasks_sync(search_tasks)  # can use serper's batching

        # Check for errors
        for search_result in search_results:
            try:
                if search_result["statusCode"] // 100 != 2:
                    logger.error(f"Error in search result: {search_result}")
                    # search_result can be {"statusCode": 400, "message": "Not enough credits"}
                    raise WebSearchAPIError() # TODO: add message, make sure it gets logged
            except KeyError:
                logger.warning("No status code in search result, assuming success.")

        # Get links from search results
        return get_links_from_search_results(search_results)
    except WebSearchAPIError as e:
        raise e
    except Exception as e:
        raise WebSearchAPIError() from e


class Queries(BaseModel):
    queries: list[str]


def get_web_search_queries_from_prompt(
    prompt, inputs: dict[str, str], chat_state: ChatState
) -> list[str]:
    """
    Get web search queries from a prompt. The prompt should ask the LLM to generate
    web search queries in the format {"queries": ["query1", "query2", ...]}
    """
    logger.info("Submitting prompt to get web search queries")
    query_generator_chain = chat_state.get_prompt_llm_chain(prompt, to_user=False)

    return enforce_pydantic_json(query_generator_chain, inputs, Queries).queries
