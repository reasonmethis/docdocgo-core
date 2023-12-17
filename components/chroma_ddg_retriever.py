from typing import Any, ClassVar

from chromadb.api.types import Where, WhereDocument
from langchain.callbacks.manager import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain.docstore.document import Document
from langchain.vectorstores.base import VectorStoreRetriever
from pydantic import Field

from utils.helpers import DELIMITER, lin_interpolate


class ChromaDDGRetriever(VectorStoreRetriever):
    """
    A retriever that uses a ChromaDDG vectorstore to find relevant documents.

    Compared to a generic VectorStoreRetriever, this retriever has the additional
    feature of accepting the `where` and `where_document` parameters in its
    `get_relevant_documents` method. These parameters are used to filter the
    documents by their metadata and contained text, respectively.

    NOTE: even though the underlying vectorstore is not explicitly required to
    be a ChromaDDG, it must be a vectorstore that supports the `where` and
    `where_document` parameters in its `similarity_search`-type methods.
    """

    verbose: bool = False  # print similarity scores and other info
    k_overshot = 20  # number of docs to return initially (prune later)
    score_threshold_overshot = 0.0  # score threshold to use initially (prune later)
    k_min = 2  # min number of docs to return after pruning
    score_threshold_min = 0.61  # use k_min if score of k_min'th doc is <= this
    k_max = 10  # max number of docs to return after pruning
    score_threshold_max = 0.76  # use k_max if score of k_max'th doc is >= this

    # get_relevant_documents() must return only docs, but we'll save scores here
    similarities: list = Field(default_factory=list)

    allowed_search_types: ClassVar[tuple[str]] = (
        "similarity",
        # "similarity_score_threshold", # NOTE can add at some point
        "mmr",
        "similarity_ddg",
    )

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
        filter: Where | None = None,  # For metadata (Langchain naming convention)
        where_document: WhereDocument | None = None,  # Filter by text in document
        **kwargs: Any,  # For additional search params
    ) -> list[Document]:
        # Combine global search kwargs with per-query search params passed here
        search_kwargs = self.search_kwargs | kwargs
        if filter is not None:
            search_kwargs["filter"] = filter
        if where_document is not None:
            search_kwargs["where_document"] = where_document

        # Perform search depending on search type
        if self.search_type == "similarity":
            docs = self.vectorstore.similarity_search(query, **search_kwargs)
        elif self.search_type == "mmr":
            docs = self.vectorstore.max_marginal_relevance_search(
                query, **search_kwargs
            )
        elif self.search_type == "similarity_ddg":
            # Main method used by DocDocGo

            # First, get more docs than we need, then we'll pare them down
            # NOTE this is because apparently Chroma can miss even the most relevant doc
            # if k (num docs to return) is not high (e.g. "Who is Big Keetie?", k = 10)
            # k_overshot = max(k := search_kwargs["k"], self.k_overshot)
            # score_threshold_overshot = min(
            #     score_threshold := search_kwargs["score_threshold"],
            #     self.score_threshold_overshot,
            # )  # usually simply 0

            docs_and_similarities_overshot = (
                self.vectorstore.similarity_search_with_relevance_scores(
                    query,
                    **(
                        search_kwargs
                        | {
                            "k": self.k_overshot,
                            "score_threshold": self.score_threshold_overshot,
                        }
                    ),
                )
            )

            if self.verbose:
                for doc, sim in docs_and_similarities_overshot:
                    print(f"[SIMILARITY: {sim:.2f}] {repr(doc.page_content[:60])}")
                print(
                    f"Before paring down: {len(docs_and_similarities_overshot)} docs."
                )

            # Now, pare down the results
            docs = []
            self.similarities = []
            for i, (doc, sim) in enumerate(docs_and_similarities_overshot):
                # If we've already found enough docs, stop
                if (k := i + 1) > self.k_max:
                    break

                # Find score_threshold if we were to have i+1 docs
                score_threshold_if_stop = lin_interpolate(
                    k,
                    self.k_min,
                    self.k_max,
                    self.score_threshold_min,
                    self.score_threshold_max,
                )

                # If we have min num of docs and similarity is below the threshold, stop
                if k > self.k_min and sim < score_threshold_if_stop:
                    break

                # Otherwise, add the doc to the list and keep going
                docs.append(doc)
                self.similarities.append(sim)
        else:
            raise ValueError(f"search_type of {self.search_type} not allowed.")

        if self.verbose:
            print(f"After paring down: {len(docs)} docs.")
            if docs:
                print(
                    f"Similarities from {self.similarities[-1]:.2f} to {self.similarities[0]:.2f}"
                )
            print(DELIMITER)
        return docs

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        raise NotImplementedError("Asynchronous retrieval not yet supported.")
