import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

IS_AZURE = bool(os.getenv("OPENAI_API_BASE"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

DEFAULT_COLLECTION_NAME = os.getenv("DEFAULT_COLLECTION_NAME", "docdocgo-documentation")
USE_CHROMA_VIA_HTTP = bool(os.getenv("USE_CHROMA_VIA_HTTP"))
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "localhost")
CHROMA_SERVER_HTTP_PORT = os.getenv("CHROMA_SERVER_HTTP_PORT", "8000")
CHROMA_SERVER_AUTH_CREDENTIALS = os.getenv("CHROMA_SERVER_AUTH_CREDENTIALS", "")
VECTORDB_DIR = os.getenv("VECTORDB_DIR", "chroma/")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo-1106")
CONTEXT_LENGTH = int(os.getenv("CONTEXT_LENGTH", 16000))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))

DEFAULT_MODE = os.getenv("DEFAULT_MODE", "/docs")


# def validate_settings():
#    global DEFAULT_COLLECTION_NAME, VECTORDB_DIR

# Check that the necessary environment variables are set
if IS_AZURE and not (EMBEDDINGS_DEPLOYMENT_NAME and CHAT_DEPLOYMENT_NAME):
    print(
        "You have set the OPENAI_API_BASE environment variable but not the other ."
        "variables necessary for Azure. Please refer to .env.example for details."
    )
    sys.exit()
elif not IS_AZURE and not os.getenv("OPENAI_API_KEY"):
    # We don't exit because we could get the key from the Streamlit app
    print(
        "WARNING: You have not set the OPENAI_API_KEY environment variable. "
        "This is ok when running in the Streamlit app, but not when running "
        "the command line app. For now, we will set it to a dummy non-empty value "
        "to avoid problems initializing the vectorstore etc. "
        "Please refer to .env.example for additional information."
    )
    os.environ["OPENAI_API_KEY"] = "DUMMY NON-EMPTY VALUE"

if not os.getenv("SERPER_API_KEY"):
    print(
        "WARNING: You have not set the SERPER_API_KEY environment variable. "
        "We will set it to a free key, but it is possible "
        "that this key will have run out of credits by now. "
        "If the Internet search functionality does not work, please set "
        "the SERPER_API_KEY environment variable to your own Google Serper API key, "
        "which you can get for free at https://serper.dev. "
    )
    # Set the free key explicitly (there is no payment info associated with this key)
    os.environ["SERPER_API_KEY"] = "71f6d411db55df3ed492bf6da727c4512be35e52"

# Verify the validity of the db path
if not os.path.isdir(VECTORDB_DIR):
    try:
        abs_path = os.path.abspath(VECTORDB_DIR)
    except Exception:
        abs_path = "INVALID PATH"
    print(
        "You have not specified a valid directory for the vector database. "
        "Please set the VECTORDB_DIR environment variable in .env, as shown in .env.example."
        f"\n\nThe path you have specified is: {VECTORDB_DIR}.\n"
        f"The absolute path resolves to: {abs_path}."
    )
    sys.exit()
