import json
import uuid
from typing import Iterable

from chromadb import ClientAPI
from dotenv import load_dotenv
from langchain_community.document_loaders import GitbookLoader

from components.chroma_ddg import ChromaDDG
from components.openai_embeddings_ddg import get_openai_embeddings
from utils.prepare import EMBEDDINGS_DIMENSIONS, get_logger
from utils.rag import rag_text_splitter
from langchain_core.documents import Document

load_dotenv(override=True)
logger = get_logger()


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
    texts: list[str], metadatas: list[dict], ids: list[str]
) -> list[Document]:
    """
    Split documents into chunks and add parent ids to the chunks' metadata.
    Returns a list of snippets (each is a Document).

    It is ok to pass an empty list of texts.
    """
    logger.info(f"Splitting {len(texts)} documents into chunks...")

    # Add parent ids to metadata (will delete, but only after it they propagate to snippets)
    for metadata, id in zip(metadatas, ids):
        metadata["parent_id"] = id

    # Split into snippets
    snippets = rag_text_splitter.create_documents(texts, metadatas)
    logger.info(f"Obtained {len(snippets)} chunks.")

    # Restore original metadata
    for metadata in metadatas:
        del metadata["parent_id"]

    return snippets


FAKE_FULL_DOC_EMBEDDING = [1.0] * EMBEDDINGS_DIMENSIONS

# TODO: remove the logic of saving to the db, leave only doc preparation. We should 
# separate concerns and reduce the number of places we write to the db.
def ingest_into_chroma(
    docs: list[Document],
    *,
    collection_name: str,
    openai_api_key: str,
    chroma_client: ClientAPI | None = None,
    save_dir: str | None = None,
    collection_metadata: dict[str, str] | None = None,
) -> ChromaDDG:
    """
    Load documents and/or collection metadata into a Chroma collection, return a vectorstore
    object.

    If collection_metadata is passed and the collection exists, the metadata will be
    replaced with the passed metadata, according to the Chroma docs.

    NOTE: Normally, the higher level agentblocks.collectionhelper.ingest_into_collection 
    should be used, which creates/updates the "created_at" and "updated_at" metadata fields.
    """
    assert bool(chroma_client) != bool(save_dir), "Invalid vector db destination"

    # Handle special case of no docs - just create/update collection with given metadata
    if not docs:
        return ChromaDDG(
            embedding_function=get_openai_embeddings(openai_api_key),
            client=chroma_client,
            persist_directory=save_dir,
            collection_name=collection_name,
            collection_metadata=collection_metadata,
            create_if_not_exists=True,
        )

    # Prepare full texts, metadatas and ids
    full_doc_ids = [str(uuid.uuid4()) for _ in range(len(docs))]
    texts = [doc.page_content for doc in docs]
    metadatas = [doc.metadata for doc in docs]

    # Split into snippets, embed and add them
    vectorstore: ChromaDDG = ChromaDDG.from_documents(
        prepare_chunks(texts, metadatas, full_doc_ids),
        embedding=get_openai_embeddings(openai_api_key),
        client=chroma_client,
        persist_directory=save_dir,
        collection_name=collection_name,
        collection_metadata=collection_metadata,
        create_if_not_exists=True,  # ok to pass (kwargs are passed to __init__)
    )

    # Add the original full docs (with fake embeddings)
    # NOTE: should be possible to add everything in one call, with some work
    fake_embeddings = [FAKE_FULL_DOC_EMBEDDING for _ in range(len(docs))]
    vectorstore.collection.add(full_doc_ids, fake_embeddings, metadatas, texts)

    logger.info(f"Ingested documents into collection {collection_name}")
    if save_dir:
        logger.info(f"Saved to {save_dir}")
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
