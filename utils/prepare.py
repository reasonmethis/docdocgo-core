import os
import sys
from dotenv import load_dotenv

load_dotenv()

IS_AZURE = bool(os.getenv("OPENAI_API_BASE"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

VECTORDB_DIR = os.getenv("VECTORDB_DIR")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo-1106")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))


def validate_settings():
    # Check that the necessary environment variables are set
    if (IS_AZURE and not (EMBEDDINGS_DEPLOYMENT_NAME and CHAT_DEPLOYMENT_NAME)) or (
        not IS_AZURE and not os.getenv("OPENAI_API_KEY")
    ):
        print("Please set the environment variables in .env, as shown in .env.example.")
        sys.exit()

    # Verify the validity of the db path
    if not VECTORDB_DIR or not os.path.isdir(VECTORDB_DIR):
        print(
            "You have not specified a valid directory for the vector database. "
            "If you have not created one yet, please do so by ingesting your "
            "documents, as described in the README. If you have already done so,"
            "then set the VECTORDB_DIR environment variable to the vector database directory."
        )

        if VECTORDB_DIR:
            print(
                f"\nThe path you have specified is: {VECTORDB_DIR}.\n"
                f"The absolute path resolves to: {os.path.abspath(VECTORDB_DIR)}."
            )
        sys.exit()
