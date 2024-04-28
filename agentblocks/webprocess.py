from typing import Callable

from pydantic import BaseModel, Field

from agentblocks.webretrieve import get_content_from_urls
from utils.type_utils import Doc
from utils.web import LinkData

DEFAULT_MIN_OK_URLS = 5
DEFAULT_INIT_BATCH_SIZE = 0  # 0 = "auto-determined"


class URLConveyer(BaseModel):
    urls: list[str]
    link_data_dict: dict[str, LinkData] = Field(default_factory=dict)
    # num_ok_urls: int = 0
    idx_first_not_done: int = 0  # done = "pushed out" by get_next_docs
    idx_first_not_tried: int = 0  # different from len(link_data_dict) if urls repeat
    num_url_retrievals: int = 0

    default_min_ok_urls: int = DEFAULT_MIN_OK_URLS
    default_init_batch_size: int = DEFAULT_INIT_BATCH_SIZE  # 0 = "auto-determined"

    def add_urls(self, urls: list[str]):
        self.urls.extend(urls)

    def retrieve_content_from_urls(
        self,
        min_ok_urls: int | None = None,  # use default_min_ok_urls if None
        init_batch_size: int | None = None,  # use default_init_batch_size if None
        batch_fetcher: Callable[[list[str]], list[str]] | None = None,
    ):
        url_retrieval_data = get_content_from_urls(
            urls=self.urls[self.idx_first_not_tried :],
            min_ok_urls=min_ok_urls
            if min_ok_urls is not None
            else self.default_min_ok_urls,
            init_batch_size=init_batch_size
            if init_batch_size is not None
            else self.default_init_batch_size,
            batch_fetcher=batch_fetcher,
        )

        self.num_url_retrievals += 1
        self.link_data_dict.update(url_retrieval_data.link_data_dict)
        self.idx_first_not_tried += url_retrieval_data.idx_first_not_tried

    def get_next_docs(self) -> list[Doc]:
        docs = []
        for url in self.urls[self.idx_first_not_done : self.idx_first_not_tried]:
            link_data = self.link_data_dict[url]
            if link_data.error:
                continue
            doc = Doc(page_content=link_data.text, metadata={"source": url})
            if link_data.num_tokens is not None:
                doc.metadata["num_tokens"] = link_data.num_tokens
            docs.append(doc)

        self.idx_first_not_done = self.idx_first_not_tried
        return docs

    def get_next_docs_with_url_retrieval(
        self,
        min_ok_urls: int | None = None,  # use default_min_ok_urls if None
        init_batch_size: int | None = None,  # use default_init_batch_size if None
        batch_fetcher: Callable[[list[str]], list[str]] | None = None,
    ) -> list[Doc]:
        if docs := self.get_next_docs():
            return docs

        # If no more docs, retrieve more content from URLs
        self.retrieve_content_from_urls(
            min_ok_urls=min_ok_urls,
            init_batch_size=init_batch_size,
            batch_fetcher=batch_fetcher,
        )
        return self.get_next_docs()
