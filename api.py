"""
The FastAPI server that enables API access to DocDocGo.
"""

import json
import os
from typing import Annotated

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
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
from utils.ingest import extract_text
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
            if user_message:
                chat_history.append((user_message, ""))
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


class ChatResponseData(BaseModel):
    content: str
    sources: list[str] | None = None
    collection_name: str | None = None
    user_facing_collection_name: str | None = None


DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY")

def decode_param(param: str | None) -> str | dict | list | None:
    return None if param is None else json.loads(param)

@app.post("/ingest/", response_model=ChatResponseData)
async def ingest(
    files: Annotated[list[UploadFile], File()],
    message: Annotated[str, Form()],
    api_key: Annotated[str, Form()],
    openai_api_key: Annotated[str | None, Form()] = None,
    chat_history: Annotated[str | None, Form()] = None,  # JSON string
    collection_name: Annotated[str | None, Form()] = None,
    access_code: Annotated[str | None, Form()] = None,
):
    """
    Handle a chat message from the user, which may include files, and return a 
    response from the bot.
    """
    # Validate the total size of the files
    max_size_bytes = 1 * 1024 * 1024  # TODO
    total_size = 0

    for ufile in files:
        # Move to the end of the file and get the position
        ufile.file.seek(0, 2)  # Seek to the end
        total_size += ufile.file.tell()  # Position = size
        ufile.file.seek(0)  # Reset for any further operations

    if total_size > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail="The total size of the files exceeds the permitted limit.",
        )

    docs, failed_files, unsupported_ext_files = extract_text(files, allow_all_ext=True)

    # We need to decode the parameters from the form data because they are JSON strings
    # or None. In particular, even string fields are passed as JSON strings. One reason
    # for this is that passing an empty string in a form field causes a 422 error.
    try:
        data = ChatRequestData(
            message=decode_param(message),
            api_key=decode_param(api_key),
            openai_api_key=decode_param(openai_api_key),
            chat_history=decode_param(chat_history),
            collection_name=decode_param(collection_name),
            access_code=decode_param(access_code),
        )
        ic(data)

        # Get the user's message and other info from the request
        # NOTE: can do this in the model itself
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

# TODO: unify the two endpoints since they have the same core logic

@app.post("/chat/", response_model=ChatResponseData)
async def chat(data: ChatRequestData = Body(...)):
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
