import json
import uuid
from typing import Iterable

from dotenv import load_dotenv
from langchain.document_loaders import GitbookLoader
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores.chroma import Chroma

from components.chroma_ddg import ChromaDDG
from components.openai_embeddings_ddg import get_openai_embeddings
from utils.output import ConditionalLogger

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


def prepare_docs(docs: list[Document], verbose: bool = False) -> list[Document]:
    """
    Prepare docs for vectorstore creation. Specifically, split into snippets and
    group duplicates together. Returns a list of snippets (each is a Document).

    It is ok to pass an empty list of docs.
    """
    clg = ConditionalLogger(verbose)

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,  # NOTE used to be 100 - can tune
        add_start_index=True,  # metadata will include start index of snippet in original doc
    )

    clg.log(f"Ingesting {len(docs)} documents")
    docs = text_splitter.split_documents(docs)
    clg.log(f"  - Split documents into {len(docs)} snippets")

    # Group duplicates together
    snippet_text_to_snippets: dict[str, list[Document]] = {}
    for snippet in reversed(docs):  # reversed means we keep the latest snippet
        try:
            snippet_text_to_snippets[snippet.page_content].append(snippet)
        except KeyError:
            snippet_text_to_snippets[snippet.page_content] = [snippet]

    # Create a single document for each group of duplicates
    docs = []
    for snippets in snippet_text_to_snippets.values():
        # Make latest snippet metadata the main one, add others' metadata
        snippet = snippets[0]
        if len(snippets) > 1:
            snippet.metadata["duplicates_metadata"] = json.dumps(
                [s.metadata for s in snippets[1:]]
            )
        docs.append(snippet)
    clg.log(f"  - After grouping duplicates - {len(docs)} snippets")
    return docs


FAKE_FULL_DOC_EMBEDDING = [10000] * 1536  # NOTE: 1536 is OpenAI's dim


def ingest_docs_into_chroma_client(
    docs: list[Document],
    *,
    collection_name: str,
    chroma_client: Chroma,
    openai_api_key: str,
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

    # First, add the full docs (with fake embeddings)
    ids = [str(uuid.uuid4()) for _ in range(len(docs))]
    texts = [doc.page_content for doc in docs]
    fake_embeddings = [FAKE_FULL_DOC_EMBEDDING for _ in range(len(docs))]

    # Now, split into snippets, embed and add those
    vectorstore = ChromaDDG.from_documents(
        prepare_docs(docs, verbose=verbose),
        embedding=get_openai_embeddings(openai_api_key),
        client=chroma_client,
        collection_name=collection_name,
        collection_metadata=collection_metadata,
    )
    clg.log(f"Ingested documents into collection {collection_name}")
    return vectorstore


# TODO: consider removing this
def create_vectorstore_ram_or_disk(
    docs: list[Document],
    *,
    collection_name: str,
    openai_api_key: str,
    save_dir: str | None = None,
    verbose: bool = False,
) -> ChromaDDG:
    """
    Create a vectorstore from a list of documents.
    """
    vectorstore = ChromaDDG.from_documents(
        prepare_docs(docs, verbose=verbose),
        embedding=get_openai_embeddings(openai_api_key),
        persist_directory=save_dir,
        collection_name=collection_name,
    )
    if verbose:
        print(f"Created collection {collection_name}")
        if save_dir:
            print(f"  - Saved to {save_dir}")
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
