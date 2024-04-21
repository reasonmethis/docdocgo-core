from typing import Callable

from pydantic import BaseModel, Field

from utils.type_utils import DDGError
from utils.web import LinkData, get_batch_url_fetcher


class URLProcessingData(BaseModel):
    urls: list[str]
    link_data_dict: dict[str, LinkData] = Field(default_factory=dict)
    num_ok_urls: int = 0

    @property
    def num_tried_urls(self):
        return len(self.link_data_dict)


def get_content_from_urls(
    urls: list[str],
    min_ok_urls: int,
    init_batch_size: int | None = None,  # auto-determined if None
    batch_fetcher: Callable[[list[str]], list[str]] | None = None,
) -> URLProcessingData:
    """
    Fetch content from a list of urls using a batch fetcher. If at least
    min_ok_urls urls are fetched successfully, return the fetched content.
    Otherwise, fetch a new batch of urls, and repeat until at least min_ok_urls
    urls are fetched successfully.

    Args:
    - urls: list of urls to fetch content from
    - min_ok_urls: minimum number of urls that need to be fetched successfully
    - init_batch_size: initial batch size to fetch content from
    - batch_fetcher: function to fetch content from a batch of urls

    Returns:
    - URLProcessingData object containing the fetched content and other data
    """
    try:
        batch_fetcher = batch_fetcher or get_batch_url_fetcher()
        init_batch_size = min(10, round(min_ok_urls * 1.2))  # NOTE: could optimize

        print(
            f"Fetching content from {len(urls)} urls:\n"
            f" - {min_ok_urls} successfully obtained URLs needed\n"
            f" - {init_batch_size} is the initial batch size\n"
        )

        res = URLProcessingData(urls=urls)
        num_urls = len(urls)

        # If, say, only 3 ok urls are still needed, we might want to try fetching 3 + extra
        num_extras = max(2, init_batch_size - min_ok_urls)

        while res.num_tried_urls < num_urls and res.num_ok_urls < min_ok_urls:
            batch_size = min(
                init_batch_size,
                min_ok_urls - res.num_ok_urls + num_extras,
            )
            batch_urls = urls[res.num_tried_urls : res.num_tried_urls + batch_size]
            batch_size = len(batch_urls)
            print(f"Fetching {batch_size} urls:")
            print("- " + "\n- ".join(batch_urls))

            # Fetch content from urls in batch
            batch_htmls = batch_fetcher(batch_urls)

            # Process fetched content
            for url, html in zip(batch_urls, batch_htmls):
                link_data = LinkData.from_raw_content(html)
                res.link_data_dict[url] = link_data
                if not link_data.error:
                    res.num_ok_urls += 1

            print(f"Total URLs processed: {res.num_tried_urls} ({num_urls} total)")
            print(f"Total successful URLs: {res.num_ok_urls} ({min_ok_urls} needed)\n")

        return res
    except Exception as e:
        raise DDGError(
            user_facing_message="Apologies, I ran into a problem trying to fetch URL content."
        ) from e
