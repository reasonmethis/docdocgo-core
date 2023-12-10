import os
from typing import Any

from chromadb import ClientAPI, PersistentClient
from chromadb.api.types import Where  # , WhereDocument
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.schema import Document
from langchain.vectorstores.chroma import Chroma, _results_to_docs_and_scores


def get_embedding_function():
    # Create the embedding function
    # (as of Aug 8, 2023, max chunk size for Azure API is 16)
    return (
        OpenAIEmbeddings(
            deployment=os.getenv("EMBEDDINGS_DEPLOYMENT_NAME"), chunk_size=16
        )
        if os.getenv("OPENAI_API_BASE")  # proxy for whether we're using Azure
        else OpenAIEmbeddings()
    )


class ChromaDDG(Chroma):
    """
    Modified Chroma vectorstore for DocDocGo.

    Specifically, it enables the kwargs passed to similarity_search_with_score
    to be passed to the __query_collection method rather than ignored,
    which allows us to pass the 'where_document' parameter.
    """

    @property
    def name(self) -> str:
        """Name of the underlying Chroma collection."""
        return self._collection.name

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


def initialize_client(path: str) -> ClientAPI:
    """
    Initialize a chroma client from a given path.
    """
    if not os.path.isdir(path):
        raise ValueError(f"Invalid chromadb path: {path}")
    return PersistentClient(path)


def load_vectorstore(collection_name: str, client: ClientAPI | None = None):
    """
    Load a ChromaDDG vectorstore from a given collection name.
    """
    if client is None:
        client = initialize_client(os.getenv("VECTORDB_DIR"))
    vectorstore = ChromaDDG(
        client=client,
        collection_name=collection_name,
        embedding_function=get_embedding_function(),
    )
    return vectorstore
