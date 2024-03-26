"""
The FastAPI server that enables API access to DocDocGo.
"""

import os

from fastapi import Body, FastAPI, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from icecream import ic
from pydantic import BaseModel

from _prepare_env import is_env_loaded
from agents.dbmanager import (
    get_access_role,
    get_short_user_id,
    get_user_facing_collection_name,
)
from components.chroma_ddg import load_vectorstore
from docdocgo import get_bot_response, get_source_links
from utils.chat_state import ChatState
from utils.helpers import DELIMITER
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.query_parsing import parse_query
from utils.type_utils import (
    AccessRole,
    JSONish,
    OperationMode,
    PairwiseChatHistory,
)

app = FastAPI()

# Allow all domains/origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

is_env_loaded = is_env_loaded  # see explanation at the end of docdocgo.py


def convert_chat_history(
    chat_history_in_role_format: list[JSONish],
) -> PairwiseChatHistory:
    """Convert the chat history into a list of tuples of the form (user_message, bot_message)"""

    chat_history = []
    user_message = ""
    for chat in chat_history_in_role_format:
        if chat["role"] == "user":
            user_message = chat["content"]
        elif chat["role"] == "assistant":
            chat_history.append((user_message, chat["content"]))
            user_message = ""
    return chat_history


# Define Pydantic models for request and response
class ChatRequestData(BaseModel):
    message: str
    api_key: str
    openai_api_key: str | None = None
    chat_history: list[JSONish] = []
    collection_name: str | None = None
    access_code: str | None = None

@app.post("/upload/")
def upload(files: list[UploadFile]):
    for file in files:
        print(file.filename)

class ChatResponseData(BaseModel):
    content: str
    sources: list[str] | None = None
    collection_name: str | None = None
    user_facing_collection_name: str | None = None


DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY")


@app.post("/chat/", response_model=ChatResponseData)
def chat(data: ChatRequestData = Body(...)):
    """Handle a chat message from the user and return a response from the bot"""
    try:
        ic(data)

        # Get the user's message and other info from the request
        message: str = data.message.strip()

        api_key: str = data.api_key  # DocDocGo API key
        openai_api_key: str = data.openai_api_key or DEFAULT_OPENAI_API_KEY
        user_id = get_short_user_id(openai_api_key)
        # TODO: use full api key as user id (but show only the short version)

        chat_history = convert_chat_history(data.chat_history)
        data.collection_name = data.collection_name or DEFAULT_COLLECTION_NAME
        collection_name = data.collection_name
        access_code = data.access_code

        # Validate the user's API key
        if api_key != os.getenv("DOCDOCGO_API_KEY"):
            print(f"Invalid API key: {api_key}")
            return ChatResponseData(content="Invalid API key.")

        # Parse the query
        parsed_query = parse_query(message)

        # Initialize vectorstore and chat state
        try:
            vectorstore = load_vectorstore(
                collection_name, openai_api_key=openai_api_key
            )
        except Exception as e:
            return ChatResponseData(
                content="Apologies, I could not load the vector database. This "
                "could be due to a misconfiguration of the environment variables "
                f"or missing files. The error reads: \n\n{e}"
            )
        chat_state = ChatState(
            operation_mode=OperationMode.FASTAPI,
            vectorstore=vectorstore,
            chat_history=chat_history,
            chat_and_command_history=chat_history,  # no difference in this context
            openai_api_key=openai_api_key,
            user_id=user_id,
            parsed_query=parsed_query,
        )

        # Validate (and cache, for this request) the user's access level
        access_role = get_access_role(chat_state, None, access_code)
        if access_role.value <= AccessRole.NONE.value:
            return ChatResponseData(
                content="Apologies, you do not have access to the collection."
            )

        # Print and validate the user's message
        print(f"GOT MESSAGE FROM {user_id}:\n{message}")
        if not message:  # LLM doesn't like empty strings
            return ChatResponseData(
                content="Apologies, I received an empty message from you."
            )

        # Get the bot's response
        result = get_bot_response(chat_state)

        # Get the reply and sources from the bot's response
        reply = result["answer"]
        sources = get_source_links(result)
    except Exception as e:
        print(e)
        return ChatResponseData(
            content="Apologies, I encountered an error while trying to "
            f"compose a response to you. The error reads:\n\n{e}"
        )

    # print("AI:", reply) - no need, we are streaming to stdout now
    print(DELIMITER)

    # Prepare the response
    rsp = ChatResponseData(content=reply)
    if sources:
        rsp.sources = sources
        print("Sources:" + "\n".join(sources) + "\n" + DELIMITER)

    # Determine the current collection name
    try:
        collection_name = result["vectorstore"].name
    except KeyError:
        pass
    rsp.collection_name = collection_name
    rsp.user_facing_collection_name = get_user_facing_collection_name(
        chat_state.user_id, collection_name
    )

    # Return the response
    return rsp


if __name__ == "__main__":
    print(
        "Starting server... (you can instead start it using `uvicorn api:app --reload`)."
    )

    from pathlib import Path

    import uvicorn

    config = {
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": "info",
        "reload": True,
        "reload_dirs": ["./"],
        "ws_ping_interval": 300,
        "ws_ping_timeout": 300,
        "timeout_keep_alive": 300,
        "use_colors": True,
        "workers": 1,
    }
    uvicorn.run(f"{Path(__file__).stem}:app", **config)
