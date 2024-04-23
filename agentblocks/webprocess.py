from agentblocks.webretrieve import URLRetrievalData


class URLConveyerBelt(URLRetrievalData):
    urls: list[str]
    num_done_urls: int = 0  # done = tried and, if ok, processed in some way

    @staticmethod
    def from_retrieval_data(url_retrieval_data: URLRetrievalData, urls: list[str]):
        upd = URLConveyerBelt(**url_retrieval_data.model_dump(), urls=urls)
        return upd
