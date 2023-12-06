from typing import Any

from langchain.schema import Document
from langchain.vectorstores import Chroma
from langchain.vectorstores.chroma import _results_to_docs_and_scores
from chromadb.api.types import Where, WhereDocument


class ChromaDDG(Chroma):
    """
    Modified Chroma vectorstore for DocDocGo.

    Specifically, it enables the kwargs passed to similarity_search_with_score
    to be passed to the __query_collection method rather than ignored,
    which allows us to pass the 'where_document' parameter.
    """

    def similarity_search_with_score(
        self,
        query: str,
        k: int,  # = DEFAULT_K,
        filter: Where | None = None,
        **kwargs: Any,
    ) -> list[tuple[Document, float]]:
        """
        Run similarity search with Chroma with distance.

        Args:
            query (str): Query text to search for.
            k (int): Number of results to return.
            filter (Where | None): Filter by metadata. Corresponds to the chromadb 'where'
                parameter. Defaults to None.
            **kwargs: Additional keyword arguments. Only 'where_document' is used, if present.

        Returns:
            list[tuple[Document, float]]: List of documents most similar to
            the query text and cosine distance in float for each.
        """

        # Determine if the passed kwargs contain a 'where_document' parameter
        # If so, we'll pass it to the __query_collection method
        try:
            possible_where_document_kwarg = {"where_document": kwargs["where_document"]}
        except KeyError:
            possible_where_document_kwarg = {}

        # Query by text or embedding, depending on whether an embedding function is present
        if self._embedding_function is None:
            results = self._Chroma__query_collection(
                query_texts=[query],
                n_results=k,
                where=filter,
                **possible_where_document_kwarg,
            )
        else:
            query_embedding = self._embedding_function.embed_query(query)
            results = self._Chroma__query_collection(
                query_embeddings=[query_embedding],
                n_results=k,
                where=filter,
                **possible_where_document_kwarg,
            )

        return _results_to_docs_and_scores(results)
