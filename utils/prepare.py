import logging
import os
import sys

from dotenv import load_dotenv

from utils.log import setup_logging

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

# Set up logging
LOG_LEVEL = os.getenv("LOG_LEVEL")
LOG_FORMAT = os.getenv("LOG_FORMAT")
setup_logging(LOG_LEVEL, LOG_FORMAT)
DEFAULT_LOGGER_NAME = os.getenv("DEFAULT_LOGGER_NAME", "ddg")


def get_logger(logger_name: str = DEFAULT_LOGGER_NAME):
    return logging.getLogger(logger_name)


# Set up the environment variables
DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY", "")
IS_AZURE = bool(os.getenv("OPENAI_API_BASE") or os.getenv("AZURE_OPENAI_API_KEY"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

DEFAULT_COLLECTION_NAME = os.getenv("DEFAULT_COLLECTION_NAME", "docdocgo-documentation")

if USE_CHROMA_VIA_HTTP := bool(os.getenv("USE_CHROMA_VIA_HTTP")):
    os.environ["CHROMA_API_IMPL"] = "rest"

# The following three variables are only used if USE_CHROMA_VIA_HTTP is True
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "localhost")
CHROMA_SERVER_HTTP_PORT = os.getenv("CHROMA_SERVER_HTTP_PORT", "8000")
CHROMA_SERVER_AUTHN_CREDENTIALS = os.getenv("CHROMA_SERVER_AUTHN_CREDENTIALS", "")

# The following variable is only used if USE_CHROMA_VIA_HTTP is False
VECTORDB_DIR = os.getenv("VECTORDB_DIR", "chroma/")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")  # rename to DEFAULT_MODEL?
CONTEXT_LENGTH = int(os.getenv("CONTEXT_LENGTH", 16000))  # it's actually more like max
# size of what we think we can feed to the model so that it doesn't get overwhelmed
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.3))

ALLOWED_MODELS = os.getenv("ALLOWED_MODELS", MODEL_NAME).split(",")
ALLOWED_MODELS = [model.strip() for model in ALLOWED_MODELS]
if MODEL_NAME not in ALLOWED_MODELS:
    raise ValueError("The default model must be in the list of allowed models.")

EMBEDDINGS_MODEL_NAME = os.getenv("EMBEDDINGS_MODEL_NAME", "text-embedding-3-large")
EMBEDDINGS_DIMENSIONS = int(os.getenv("EMBEDDINGS_DIMENSIONS", 3072))

LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))

DEFAULT_MODE = os.getenv("DEFAULT_MODE", "/kb")

INCLUDE_ERROR_IN_USER_FACING_ERROR_MSG = bool(
    os.getenv("INCLUDE_ERROR_IN_USER_FACING_ERROR_MSG")
)

BYPASS_SETTINGS_RESTRICTIONS = bool(os.getenv("BYPASS_SETTINGS_RESTRICTIONS"))
BYPASS_SETTINGS_RESTRICTIONS_PASSWORD = os.getenv(
    "BYPASS_SETTINGS_RESTRICTIONS_PASSWORD"
)

DOMAIN_NAME_FOR_SHARING = os.getenv("DOMAIN_NAME_FOR_SHARING", "shared")

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", 100 * 1024 * 1024))

INITIAL_TEST_QUERY_STREAMLIT = os.getenv("INITIAL_QUERY_STREAMLIT")

# Check that the necessary environment variables are set
DUMMY_OPENAI_API_KEY_PLACEHOLDER = "DUMMY NON-EMPTY VALUE"

if IS_AZURE and not (
    EMBEDDINGS_DEPLOYMENT_NAME
    and CHAT_DEPLOYMENT_NAME
    and os.getenv("AZURE_OPENAI_API_KEY")
    and os.getenv("OPENAI_API_BASE")
):
    raise ValueError(
        "You have set some but not all environment variables necessary to utilize the "
        "Azure OpenAI API endpoint. Please refer to .env.example for details."
    )
elif not IS_AZURE and not DEFAULT_OPENAI_API_KEY:
    # We don't exit because we could get the key from the Streamlit app
    print(
        "WARNING: You have not set the DEFAULT_OPENAI_API_KEY environment variable. "
        "This is ok when running the Streamlit app, but not when running "
        "the command line app. For now, we will set it to a dummy non-empty value "
        "to avoid problems initializing the vectorstore etc. "
        "Please refer to .env.example for additional information."
    )
    os.environ["DEFAULT_OPENAI_API_KEY"] = DUMMY_OPENAI_API_KEY_PLACEHOLDER
    DEFAULT_OPENAI_API_KEY = DUMMY_OPENAI_API_KEY_PLACEHOLDER
    # TODO investigate the behavior when this happens

if not os.getenv("SERPER_API_KEY") and not os.getenv("IGNORE_LACK_OF_SERPER_API_KEY"):
    raise ValueError(
        "You have not set the SERPER_API_KEY environment variable, "
        "which is necessary for the Internet search functionality."
        "Pease set the SERPER_API_KEY environment variable to your Google Serper API key, "
        "which you can get for free, with no credit card, at https://serper.dev. "
        "This free key will allow you to make about 1250 searches until payment is required.\n\n"
        "If you want to supress this error, set the IGNORE_LACK_OF_SERPER_API_KEY environment "
        "variable to any non-empty value. You can then use features that do not require the "
        "Internet search functionality."
    )

# Verify the validity of the db path
if not os.getenv("USE_CHROMA_VIA_HTTP") and not os.path.isdir(VECTORDB_DIR):
    try:
        abs_path = os.path.abspath(VECTORDB_DIR)
    except Exception:
        abs_path = "INVALID PATH"
    raise ValueError(
        "You have not specified a valid directory for the vector database. "
        "Please set the VECTORDB_DIR environment variable in .env, as shown in .env.example. "
        "Alternatively, if you have a Chroma DB server running, you can set the "
        "USE_CHROMA_VIA_HTTP environment variable to any non-empty value. "
        f"\n\nThe path you have specified is: {VECTORDB_DIR}.\n"
        f"The absolute path resolves to: {abs_path}."
    )


is_env_loaded = True
