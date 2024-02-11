import os
import sys

from dotenv import load_dotenv

load_dotenv(override=True)

# Import chromadb while making it think sqlite3 has a new enough version.
# This is necessary because the version of sqlite3 in Streamlit Share is too old.
# We don't actually use sqlite3 in a Streamlit Share context, because we use HttpClient,
# so it's fine to use the app there despite ending up with an incompatible sqlite3.
sys.modules["sqlite3"] = lambda: None
sys.modules["sqlite3"].sqlite_version_info = (42, 42, 42)
__import__("chromadb")
del sys.modules["sqlite3"]
__import__("sqlite3")  # import here because chromadb was supposed to import it

IS_AZURE = bool(os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_API_KEY"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

DEFAULT_COLLECTION_NAME = os.getenv("DEFAULT_COLLECTION_NAME", "docdocgo-documentation")

if USE_CHROMA_VIA_HTTP := bool(os.getenv("USE_CHROMA_VIA_HTTP")):
    os.environ["CHROMA_API_IMPL"] = "rest"

# The following three variables are only used if USE_CHROMA_VIA_HTTP is True
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "localhost")
CHROMA_SERVER_HTTP_PORT = os.getenv("CHROMA_SERVER_HTTP_PORT", "8000")
CHROMA_SERVER_AUTH_CREDENTIALS = os.getenv("CHROMA_SERVER_AUTH_CREDENTIALS", "")

# The following variable is only used if USE_CHROMA_VIA_HTTP is False
VECTORDB_DIR = os.getenv("VECTORDB_DIR", "chroma/")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo-0125")
CONTEXT_LENGTH = int(os.getenv("CONTEXT_LENGTH", 16000))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.3))

EMBEDDINGS_MODEL_NAME = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-3-large")
EMBEDDINGS_DIMENSIONS = int(os.getenv("EMBEDDINGS_DIMENSIONS", 3072))

LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))

DEFAULT_MODE = os.getenv("DEFAULT_MODE", "/docs")

# Check that the necessary environment variables are set
DUMMY_OPENAI_API_KEY_PLACEHOLDER = "DUMMY NON-EMPTY VALUE"

if IS_AZURE and not (
    EMBEDDINGS_DEPLOYMENT_NAME
    and CHAT_DEPLOYMENT_NAME
    and os.getenv("AZURE_OPENAI_API_KEY")
    and os.getenv("OPENAI_API_BASE")
):
    print(
        "You have set some but not all environment variables necessary to utilize the "
        "Azure OpenAI API endpoint. Please refer to .env.example for details."
    )
    sys.exit()
elif not IS_AZURE and not os.getenv("DEFAULT_OPENAI_API_KEY"):
    # We don't exit because we could get the key from the Streamlit app
    print(
        "WARNING: You have not set the DEFAULT_OPENAI_API_KEY environment variable. "
        "This is ok when running the Streamlit app, but not when running "
        "the command line app. For now, we will set it to a dummy non-empty value "
        "to avoid problems initializing the vectorstore etc. "
        "Please refer to .env.example for additional information."
    )
    os.environ["DEFAULT_OPENAI_API_KEY"] = DUMMY_OPENAI_API_KEY_PLACEHOLDER
    # TODO investigate the behavior when this happens

if not os.getenv("SERPER_API_KEY"):
    print(
        "WARNING: You have not set the SERPER_API_KEY environment variable. "
        "We will set it to a free key, but it is possible "
        "that this key will have run out of credits by now. "
        "If the Internet search functionality does not work, please set "
        "the SERPER_API_KEY environment variable to your own Google Serper API key, "
        "which you can get for free, without a credit card, at https://serper.dev. "
    )
    # Set the free key explicitly (there is no payment info associated with this key)
    os.environ["SERPER_API_KEY"] = "dc1e2534afe8cbd358cbb53cb84f437a48b536fd"


# Verify the validity of the db path
if not os.getenv("USE_CHROMA_VIA_HTTP") and not os.path.isdir(VECTORDB_DIR):
    try:
        abs_path = os.path.abspath(VECTORDB_DIR)
    except Exception:
        abs_path = "INVALID PATH"
    print(
        "You have not specified a valid directory for the vector database. "
        "Please set the VECTORDB_DIR environment variable in .env, as shown in .env.example. "
        "Alternatively, if you have a Chroma DB server running, you can set the "
        "USE_CHROMA_VIA_HTTP environment variable to any non-empty value. "
        f"\n\nThe path you have specified is: {VECTORDB_DIR}.\n"
        f"The absolute path resolves to: {abs_path}."
    )
    sys.exit()


is_env_loaded = True
