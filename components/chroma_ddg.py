import os
from typing import Any

from chromadb import ClientAPI, HttpClient, PersistentClient
from chromadb.api.types import Where  # , WhereDocument
from chromadb.config import Settings
from langchain.schema import Document
from langchain.vectorstores.chroma import Chroma
from langchain_community.vectorstores.chroma import _results_to_docs_and_scores

from components.openai_embeddings_ddg import get_openai_embeddings
from utils.prepare import (
    CHROMA_SERVER_AUTH_CREDENTIALS,
    CHROMA_SERVER_HOST,
    CHROMA_SERVER_HTTP_PORT,
    USE_CHROMA_VIA_HTTP,
    VECTORDB_DIR,
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

    @property
    def collection(self) -> Chroma:
        """The underlying Chroma collection."""
        return self._collection

    @property
    def client(self) -> ClientAPI:
        """The underlying Chroma client."""
        return self._client

    def get_collection_metadata(self) -> dict[str, Any] | None:
        """Get metadata for the underlying Chroma collection."""
        return self._collection.metadata

    def set_collection_metadata(self, metadata: dict[str, Any]) -> None:
        """Set metadata for the underlying Chroma collection."""
        self._collection.modify(metadata=metadata)
        # self._client.persist()  # won't be needed when we can switch to v >= 0.4.0

    def rename_collection(self, new_name: str) -> None:
        """Rename the underlying Chroma collection."""
        self._collection.modify(name=new_name)
        # self._client.persist()  # won't be needed when we can switch to v >= 0.4.0

    def delete_collection(self, collection_name: str) -> None:
        """Delete the underlying Chroma collection."""
        self._client.delete_collection(collection_name)
        # self._client.persist()  # won't be needed when we can switch to v >= 0.4.0

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
            list[tuple[Document, float]]: list of documents most similar to
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


def exists_collection(
    collection_name: str,
    client: ClientAPI,
) -> bool:
    """
    Check if a collection exists.
    """
    # NOTE: Alternative: return collection_name in {x.name for x in client.list_collections()}
    try:
        client.get_collection(collection_name)
        return True
    except Exception as e:
        if "does not exist" in str(e):
            return False  # collection does not exist
        raise e


def initialize_client() -> ClientAPI:
    """
    Initialize a chroma client from a given path.
    """
    if USE_CHROMA_VIA_HTTP:
        return HttpClient(
            host=CHROMA_SERVER_HOST,  # must provide host and port explicitly...
            port=CHROMA_SERVER_HTTP_PORT,  # ...if the env vars are different from defaults
            settings=Settings(
                chroma_client_auth_provider="chromadb.auth.token.TokenAuthClientProvider",
                chroma_client_auth_token_transport_header="X_CHROMA_TOKEN",
                chroma_client_auth_credentials=CHROMA_SERVER_AUTH_CREDENTIALS,
                anonymized_telemetry=False,
            ),
        )
    if not isinstance(VECTORDB_DIR, str) or not os.path.isdir(VECTORDB_DIR):
        # NOTE: interestingly, isdir(None) returns True, hence the additional check
        raise ValueError(f"Invalid chromadb path: {VECTORDB_DIR}")

    return PersistentClient(VECTORDB_DIR, settings=Settings(anonymized_telemetry=False))
    # return Client(Settings(chroma_db_impl="duckdb+parquet", persist_directory=path))


def ensure_chroma_client(client: ClientAPI | None = None) -> ClientAPI:
    """
    Ensure that a chroma client is initialized and return it.
    """
    return client or initialize_client()


def load_vectorstore(
    collection_name: str, *, openai_api_key: str, client: ClientAPI | None = None
):
    """
    Load a ChromaDDG vectorstore from a given collection name.
    """
    vectorstore = ChromaDDG(
        client=ensure_chroma_client(client),
        collection_name=collection_name,
        embedding_function=get_openai_embeddings(openai_api_key),
    )
    return vectorstore
