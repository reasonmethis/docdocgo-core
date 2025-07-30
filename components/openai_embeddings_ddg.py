import os

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from utils.prepare import EMBEDDINGS_DIMENSIONS, EMBEDDINGS_MODEL_NAME, IS_AZURE


def get_openai_embeddings(
    api_key: str | None = None,
    embeddings_model_name: str = EMBEDDINGS_MODEL_NAME,
    embeddings_dimensions: int = EMBEDDINGS_DIMENSIONS,
) -> Embeddings:
    # Create the embeddings object, pulling current values of env vars
    # (as of Aug 8, 2023, max chunk size for Azure API is 16)
    return (
        OpenAIEmbeddings(  # NOTE: should be able to simplify this
            deployment=os.getenv("EMBEDDINGS_DEPLOYMENT_NAME"), chunk_size=16
        )
        if IS_AZURE
        else OpenAIEmbeddings(
            api_key=api_key or "",
            model=embeddings_model_name,
            dimensions=None
            if embeddings_model_name == "text-embeddings-ada-002"
            else embeddings_dimensions,
        )  # NOTE: if empty API key, will throw
    )


# class OpenAIEmbeddingsDDG(Embeddings):
#     """
#     Custom version of OpenAIEmbeddings for DocDocGo. Unlike the original,
#     an object of this class will pull the current values of env vars every time.
#     This helps in situations where the user has changed env vars such as
#     OPENROUTER_API_KEY, as is possible in the Streamlit app.

#     This way is also more consistent with the behavior of e.g. ChatOpenAI, which
#     always uses the current values of env vars when querying the OpenAI API.
#     """

#     @staticmethod
#     def get_fresh_openai_embeddings():
#         # Create the embeddings object, pulling current values of env vars
#         # (as of Aug 8, 2023, max chunk size for Azure API is 16)
#         return (
#             OpenAIEmbeddings(  # NOTE: should be able to simplify this
#                 deployment=os.getenv("EMBEDDINGS_DEPLOYMENT_NAME"), chunk_size=16
#             )
#             if os.getenv("OPENAI_API_BASE")  # proxy for whether we're using Azure
#             else OpenAIEmbeddings()
#         )

#     def embed_documents(self, texts: list[str]) -> list[list[float]]:
#         """Embed search docs."""
#         return self.get_fresh_openai_embeddings().embed_documents(texts)

#     def embed_query(self, text: str) -> list[float]:
#         """Embed query text."""
#         return self.get_fresh_openai_embeddings().embed_query(text)

#     async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
#         """Asynchronous Embed search docs."""
#         return await self.get_fresh_openai_embeddings().aembed_documents(texts)

#     async def aembed_query(self, text: str) -> list[float]:
#         """Asynchronous Embed query text."""
#         return await self.get_fresh_openai_embeddings().aembed_query(text)
