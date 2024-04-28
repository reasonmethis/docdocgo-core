from typing import Callable

from pydantic import BaseModel, Field

from utils.prepare import get_logger
from utils.type_utils import DDGError
from utils.web import LinkData, get_batch_url_fetcher

logger = get_logger()


class URLRetrievalData(BaseModel):
    urls: list[str]
    link_data_dict: dict[str, LinkData] = Field(default_factory=dict)
    num_ok_urls: int = 0
    idx_first_not_tried: int = 0  # different from len(link_data_dict) if urls repeat


MAX_INIT_BATCH_SIZE = 10


def get_content_from_urls(
    urls: list[str],
    min_ok_urls: int,
    init_batch_size: int = 0,  # auto-determined if 0
    batch_fetcher: Callable[[list[str]], list[str]] | None = None,
) -> URLRetrievalData:
    """
    Fetch content from a list of urls using a batch fetcher. If at least
    min_ok_urls urls are fetched successfully, return the fetched content.
    Otherwise, fetch a new batch of urls, and repeat until at least min_ok_urls
    urls are fetched successfully.

    If there are duplicate URLs

    Args:
    - urls: list of urls to fetch content from
    - min_ok_urls: minimum number of urls that need to be fetched successfully
    - init_batch_size: initial batch size to fetch content from
    - batch_fetcher: function to fetch content from a batch of urls

    Returns:
    - URLRetrievalData: object containing the fetched content
    """
    try:
        batch_fetcher = batch_fetcher or get_batch_url_fetcher()
        init_batch_size = init_batch_size or min(
            MAX_INIT_BATCH_SIZE, round(min_ok_urls * 1.2)
        )  # NOTE: could optimize

        logger.info(
            f"Fetching content from {len(urls)} urls:\n"
            f" - {min_ok_urls} successfully obtained URLs needed\n"
            f" - {init_batch_size} is the initial batch size\n"
        )

        res = URLRetrievalData(urls=urls)
        num_urls = len(urls)
        url_set = set()  # to keep track of unique urls

        # If, say, only 3 ok urls are still needed, we might want to try fetching 3 + extra
        num_extras = max(2, init_batch_size - min_ok_urls)

        while res.num_ok_urls < min_ok_urls:
            batch_size = min(
                init_batch_size,
                min_ok_urls - res.num_ok_urls + num_extras,
            )
            batch_urls = []
            for url in urls[res.idx_first_not_tried :]:
                if len(batch_urls) == batch_size:
                    break
                if url in url_set:
                    continue
                batch_urls.append(url)
                url_set.add(url)
                res.idx_first_not_tried += 1

            if (batch_size := len(batch_urls)) == 0:
                break  # no more urls to fetch

            logger.info(f"Fetching {batch_size} urls:\n- " + "\n- ".join(batch_urls))

            # Fetch content from urls in batch
            batch_htmls = batch_fetcher(batch_urls)

            # Process fetched content
            for url, html in zip(batch_urls, batch_htmls):
                link_data = LinkData.from_raw_content(html)
                res.link_data_dict[url] = link_data
                if not link_data.error:
                    res.num_ok_urls += 1

            logger.info(
                f"Total URLs processed: {res.idx_first_not_tried} ({num_urls} total)\n"
                f"Total successful URLs: {res.num_ok_urls} ({min_ok_urls} needed)\n"
            )

        return res
    except Exception as e:
        raise DDGError(
            user_facing_message="Apologies, I ran into a problem trying to fetch URL content."
        ) from e
