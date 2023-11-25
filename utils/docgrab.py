from typing import Iterable
import json
import os
from dotenv import load_dotenv

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from components.chroma_ddg import ChromaDDG

from langchain.document_loaders import GitbookLoader
from langchain.schema import Document

load_dotenv()


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


def create_vectorstore(docs, save_dir=None) -> ChromaDDG:
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,  # NOTE used to be 100 - can tune
        add_start_index=True,  # metadata will include start index of snippet in original doc
    )

    print(f"Creating vectorstore with {len(docs)} documents")
    docs = text_splitter.split_documents(docs)
    print(f"  - Split documents into {len(docs)} snippets")

    # Group duplicates together
    snippet_text_to_snippets: dict[
        str, list[Document]
    ] = {}  # all snippets with same text
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
    print(f"  - After grouping duplicates - {len(docs)} snippets")

    # Create vectorstore
    # (as of Aug 8, 2023, max chunk size for Azure API is 16)
    embeddings = (
        OpenAIEmbeddings(
            deployment=os.getenv("EMBEDDINGS_DEPLOYMENT_NAME"), chunk_size=16
        )
        if os.getenv("OPENAI_API_BASE")  # proxy for whether we're using Azure
        else OpenAIEmbeddings()
    )

    vectorstore = ChromaDDG.from_documents(docs, embeddings, persist_directory=save_dir)
    print("Created vectorstore")
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
