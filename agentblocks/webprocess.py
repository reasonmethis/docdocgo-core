from langchain_core.documents import Document
from pydantic import BaseModel, Field

from agentblocks.webretrieve import URLRetrievalData
from utils.web import LinkData


class URLConveyerBelt(BaseModel):
    urls: list[str]
    link_data_dict: dict[str, LinkData] = Field(default_factory=dict)
    # num_ok_urls: int = 0
    idx_first_not_done: int = 0  # done = "pushed out" by get_next_docs
    idx_first_not_tried: int = 0  # different from len(link_data_dict) if urls repeat

    @staticmethod
    def from_retrieval_data(url_retrieval_data: URLRetrievalData):
        return URLConveyerBelt(
            urls=url_retrieval_data.urls,
            link_data_dict=url_retrieval_data.link_data_dict,
            idx_first_not_tried=url_retrieval_data.idx_first_not_tried,
            idx_first_not_done=0,
        )

    def add_urls(self, urls: list[str]):
        self.urls.extend(urls)

    def add_retrieval_data(
        self, link_data_dict: dict[str, LinkData], new_idx_first_not_tried: int
    ):
        # NOTE: not using URLRetrievalData to avoid confusion if urls are different
        self.link_data_dict.update(link_data_dict)
        self.idx_first_not_tried = new_idx_first_not_tried

    def get_next_docs(self):
        docs = []
        for url in self.urls[self.idx_first_not_done : self.idx_first_not_tried]:
            link_data = self.link_data_dict[url]
            if link_data.error:
                continue
            doc = Document(page_content=link_data.text, metadata={"source": url})
            if link_data.num_tokens is not None:
                doc.metadata["num_tokens"] = link_data.num_tokens
            docs.append(doc)

        self.idx_first_not_done = self.idx_first_not_tried
        return docs
