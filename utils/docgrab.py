import json
import os
import uuid
from typing import Iterable

from chromadb import ClientAPI
from dotenv import load_dotenv
from langchain_community.document_loaders import GitbookLoader
from langchain.schema import Document

from components.chroma_ddg import ChromaDDG
from components.openai_embeddings_ddg import get_openai_embeddings
from utils.output import ConditionalLogger
from utils.prepare import EMBEDDINGS_DIMENSIONS
from utils.rag import text_splitter

load_dotenv(override=True)


class JSONLDocumentLoader:
    def __init__(self, file_path: str, max_docs=None) -> None:
        self.file_path = file_path
        self.max_docs = max_docs

    def load(self) -> list[Document]:
        docs = load_docs_from_jsonl(self.file_path)
        if self.max_docs is None or self.max_docs > len(docs):
            return docs
        return docs[: self.max_docs]


def save_docs_to_jsonl(docs: Iterable[Document], file_path: str) -> None:
    with open(file_path, "a") as f:
        for doc in docs:
            f.write(doc.json() + "\n")


def load_docs_from_jsonl(file_path: str) -> list[Document]:
    docs = []
    with open(file_path, "r") as f:
        for line in f:
            data = json.loads(line)
            doc = Document(**data)
            docs.append(doc)
    return docs


def load_gitbook(root_url: str) -> list[Document]:
    all_pages_docs = GitbookLoader(root_url, load_all_paths=True).load()
    return all_pages_docs


def prepare_chunks(
    texts: list[str], metadatas: list[dict], ids: list[str], verbose: bool = False
) -> list[Document]:
    """
    Split documents into chunks and add parent ids to the chunks' metadata.
    Returns a list of snippets (each is a Document).

    It is ok to pass an empty list of texts.
    """
    clg = ConditionalLogger(verbose)
    clg.log(f"Splitting {len(texts)} documents into chunks...")

    # Add parent ids to metadata
    for metadata, id in zip(metadatas, ids):
        metadata["parent_id"] = id

    # Split into snippets
    snippets = text_splitter.create_documents(texts, metadatas)
    clg.log(f"Obtained {len(snippets)} chunks.")

    # Restore original metadata
    for metadata in metadatas:
        del metadata["parent_id"]

    return snippets


FAKE_FULL_DOC_EMBEDDING = [1.0] * EMBEDDINGS_DIMENSIONS


def ingest_docs_into_chroma(
    docs: list[Document],
    *,
    collection_name: str,
    openai_api_key: str,
    chroma_client: ClientAPI | None = None,
    save_dir: str | None = None,
    collection_metadata: dict | None = None,
    verbose: bool = False,
) -> ChromaDDG:
    """
    Ingest a list of documents and return a vectorstore.

    If collection_metadata is passed and the collection exists, the metadata will be
    replaced with the passed metadata, according to the Chroma docs.
    """
    # NOTE: it looks like this appends to the existing collection if it exists
    # (we use it in ingest_local_docs.py for both creating a new collection and
    # adding to an existing one). But I am still not 100% sure if the returned vectorstore
    # incorporates the existing docs (I think it does, but I need to double check).
    clg = ConditionalLogger(verbose)
    assert bool(chroma_client) != bool(save_dir), "Invalid vector db destination"

    # Prepare full texts, metadatas and ids
    full_doc_ids = [str(uuid.uuid4()) for _ in range(len(docs))]
    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]

    # Split into snippets, embed and add them
    vectorstore: ChromaDDG = ChromaDDG.from_documents(
        prepare_chunks(texts, metadatas, full_doc_ids, verbose=verbose),
        embedding=get_openai_embeddings(openai_api_key),
        client=chroma_client,
        persist_directory=save_dir,
        collection_name=collection_name,
        collection_metadata=collection_metadata,
    )

    # Add the original full docs (with fake embeddings)
    fake_embeddings = [FAKE_FULL_DOC_EMBEDDING for _ in range(len(docs))]
    vectorstore.collection.add(full_doc_ids, fake_embeddings, metadatas, texts)

    clg.log(f"Ingested documents into collection {collection_name}")
    if save_dir:
        clg.log(f"Saved to {save_dir}")
    return vectorstore


if __name__ == "__main__":
    pass
    # download all pages from gitbook and save to jsonl
    # all_pages_docs = load_gitbook(GITBOOK_ROOT_URL)
    # print(f"Loaded {len(all_pages_docs)} documents")
    # save_docs_to_jsonl(all_pages_docs, "docs.jsonl")

    # load from jsonl
    # docs = load_docs_from_jsonl("docs.jsonl")
    # print(f"Loaded {len(docs)} documents")
