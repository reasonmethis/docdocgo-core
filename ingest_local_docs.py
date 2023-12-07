# Print an intro message before loading imports, which can take a while
print("-" * 70 + "\n" + " " * 20 + "Local Document Ingestion\n" + "-" * 70 + "\n")

import os
import sys
from langchain.document_loaders import TextLoader, DirectoryLoader
from components.chroma_ddg import initialize_client
from utils.docgrab import (
    create_vectorstore_ram_or_disk,
    JSONLDocumentLoader,
    ingest_docs_into_chroma_client,
)
from utils.helpers import clear_directory, is_directory_empty, print_no_newline

if __name__ == "__main__":
    DOCS_TO_INGEST_DIR_OR_FILE = os.getenv("DOCS_TO_INGEST_DIR_OR_FILE")
    COLLECTON_NAME_FOR_INGESTED_DOCS = os.getenv("COLLECTON_NAME_FOR_INGESTED_DOCS")
    VECTORDB_DIR = os.getenv("VECTORDB_DIR")

    if (
        not DOCS_TO_INGEST_DIR_OR_FILE
        or not VECTORDB_DIR
        or not COLLECTON_NAME_FOR_INGESTED_DOCS
    ):
        print(
            "Please set DOCS_TO_INGEST_DIR_OR_FILE, COLLECTON_NAME_FOR_INGESTED_DOC, "
            "and VECTORDB_DIR in `.env`."
        )
        sys.exit()
    if not os.path.exists(DOCS_TO_INGEST_DIR_OR_FILE):
        print(f"{DOCS_TO_INGEST_DIR_OR_FILE} does not exist.")
        sys.exit()

    # Validate the save directory
    if not os.path.isdir(VECTORDB_DIR):
        if os.path.exists(VECTORDB_DIR):
            print(f"{VECTORDB_DIR} is not a directory.")
            sys.exit()
        print(f"{VECTORDB_DIR} is not an existing directory.")
        ans = input("Do you want to create it? [y/N] ")
        if ans.lower() != "y":
            sys.exit()
        else:
            try:
                os.makedirs(VECTORDB_DIR)
            except Exception as e:
                print(f"Could not create {VECTORDB_DIR}: {e}")
                sys.exit()

    # Check if the save directory is empty; if not, give the user options
    if is_directory_empty(VECTORDB_DIR):
        is_new_db = True
    else:
        ans = input(
            f"{VECTORDB_DIR} is not empty. Please select an option:\n"
            "1. Overwrite\n2. Append\n3. Cancel\n"
        )
        if ans not in {"1", "2"}:
            sys.exit()
        is_new_db = ans == "1"
        if is_new_db:
            print_no_newline(f"Deleting files and folders in {VECTORDB_DIR}...")
            clear_directory(VECTORDB_DIR)
            print("Done!")

    # Confirm the ingestion
    print(f"You are about to ingest documents from: {DOCS_TO_INGEST_DIR_OR_FILE}")
    print(f"The vector database will be saved to: {VECTORDB_DIR}")
    print(f"The collection name will be: {COLLECTON_NAME_FOR_INGESTED_DOCS}")
    print(f"Is this a new database? {'Yes' if is_new_db else 'No'}\n")

    print("ATTENTION: This will incur some cost on your OpenAI account.")

    if input("Press Enter to proceed. Any non-empty input will cancel the procedure: "):
        print("Ingestion cancelled. Exiting")
        sys.exit()

    # Load the documents
    print_no_newline("Loading your documents...")
    if os.path.isfile(DOCS_TO_INGEST_DIR_OR_FILE):
        if DOCS_TO_INGEST_DIR_OR_FILE.endswith(".jsonl"):
            loader = JSONLDocumentLoader(DOCS_TO_INGEST_DIR_OR_FILE)
        else:
            loader = TextLoader(DOCS_TO_INGEST_DIR_OR_FILE, autodetect_encoding=True)
    else:
        loader = DirectoryLoader(
            DOCS_TO_INGEST_DIR_OR_FILE,
            loader_cls=TextLoader,  # default is Unstructured but python-magic hangs on import
            loader_kwargs={"autodetect_encoding": True},
        )
    docs = loader.load()
    print("Done!")

    # Create the vectorstore (this will print messages regarding the status)
    if is_new_db:
        create_vectorstore_ram_or_disk(
            docs, COLLECTON_NAME_FOR_INGESTED_DOCS, save_dir=VECTORDB_DIR, verbose=True
        )
    else:
        chroma_client = initialize_client(VECTORDB_DIR)
        ingest_docs_into_chroma_client(
            docs, COLLECTON_NAME_FOR_INGESTED_DOCS, chroma_client, verbose=True
        )
