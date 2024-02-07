
from typing import Any

from utils.algo import interleave_iterables, remove_duplicates_keep_order


def extract_domain(url: str):
    try:
        full_domain = url.split("://")[-1].split("/")[0]  # blah.blah.domain.com
        return ".".join(full_domain.split(".")[-2:])  # domain.com
    except Exception:
        return ""


domain_blacklist = ["youtube.com"]


def get_links(search_results: list[dict[str, Any]]):
    links_for_each_query = [
        [x["link"] for x in search_result.get("organic", []) if "link" in x]
        for search_result in search_results
    ]  # [[links for query 1], [links for query 2], ...]

    # from pprint import pprint
    # print("Links for each query:")
    # pprint(links_for_each_query)
    # print("-" * 100)

    # NOTE: can ask LLM to decide which links to keep
    return [
        link
        for link in remove_duplicates_keep_order(
            interleave_iterables(links_for_each_query)
        )
        if extract_domain(link) not in domain_blacklist
    ]
