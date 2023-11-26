# Print an intro message before loading imports, which can take a while
print("-" * 70 + "\n" + " " * 20 + "Local Document Ingestion\n" + "-" * 70 + "\n")

import os
import sys
from langchain.document_loaders import TextLoader, DirectoryLoader
from utils import docgrab
from utils.helpers import is_directory_empty

if __name__ == "__main__":
    DOCS_TO_INGEST_DIR_OR_FILE = os.getenv("DOCS_TO_INGEST_DIR_OR_FILE")
    SAVE_VECTORDB_DIR = os.getenv("SAVE_VECTORDB_DIR")

    if not DOCS_TO_INGEST_DIR_OR_FILE or not SAVE_VECTORDB_DIR:
        print("Please set DOCS_TO_INGEST_DIR_OR_FILE and SAVE_VECTORDB_DIR in `.env`.")
        sys.exit()
    if not os.path.exists(DOCS_TO_INGEST_DIR_OR_FILE):
        print(f"{DOCS_TO_INGEST_DIR_OR_FILE} does not exist.")
    if not os.path.isdir(SAVE_VECTORDB_DIR):
        print(f"{SAVE_VECTORDB_DIR} is not an existing directory.")
        ans = input("Do you want to create it? [y/N] ")
        if ans.lower() != "y":
            sys.exit()
        else:
            try:
                os.makedirs(SAVE_VECTORDB_DIR)
            except Exception as e:
                print(f"Could not create {SAVE_VECTORDB_DIR}: {e}")
                sys.exit()    
    if not is_directory_empty(SAVE_VECTORDB_DIR):
        print(f"{SAVE_VECTORDB_DIR} is not empty. Please specify an empty directory.")
        sys.exit()

    print(f"You are about to ingest documents from: {DOCS_TO_INGEST_DIR_OR_FILE}")
    print(f"The vector database will be saved to: {SAVE_VECTORDB_DIR}\n")

    print("ATTENTION: This will incur some cost on your OpenAI account.")

    if input("Press Enter to proceed. Any non-empty input will cancel the procedure: "):
        print("Ingestion cancelled. Exiting")
        sys.exit()

    print("Loading your documents...", end="", flush=True)
    if os.path.isfile(DOCS_TO_INGEST_DIR_OR_FILE):
        if DOCS_TO_INGEST_DIR_OR_FILE.endswith(".jsonl"):
            loader = docgrab.JSONLDocumentLoader(DOCS_TO_INGEST_DIR_OR_FILE)
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
    vectorstore = docgrab.create_vectorstore(docs, save_dir=SAVE_VECTORDB_DIR or None)
