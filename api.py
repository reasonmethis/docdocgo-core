"""
The FastAPI server that enables API access to DocDocGo.
"""

import json
import os
import traceback
from typing import Optional, Annotated

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
from utils.chat_state import ChatState, ScheduledQueries
from utils.helpers import DELIMITER
from utils.ingest import extract_text, format_ingest_failure
from utils.prepare import (
    BYPASS_SETTINGS_RESTRICTIONS,
    BYPASS_SETTINGS_RESTRICTIONS_PASSWORD,
    DEFAULT_COLLECTION_NAME,
    MAX_UPLOAD_BYTES,
)
from utils.query_parsing import parse_query
from utils.type_utils import (
    AccessRole,
    BotSettings,
    ChatMode,
    Instruction,
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


# Define Pydantic models for request and response
class ChatRequestData(BaseModel):
    message: str
    api_key: str
    openai_api_key: str | None = None
    chat_history: list[JSONish] = []
    collection_name: str | None = None
    access_codes_cache: dict[str, str] | None = None  # coll name -> access_code
    scheduled_queries_str: str | None = None  # JSON string of ScheduledQueries
    bot_settings: BotSettings | None = None


class ChatResponseData(BaseModel):
    content: str
    sources: list[str] | None = None
    collection_name: str | None = None
    user_facing_collection_name: str | None = None
    instructions: list[Instruction] | None = None
    scheduled_queries_str: str | None = None  # JSON string of ScheduledQueries


DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY")


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


def decode_param(param: str | None) -> str | dict | list | None:
    return None if param is None else json.loads(param)


async def handle_chat_or_ingest_request(
    data: ChatRequestData, files: Optional[list[UploadFile]] = None
):
    files = [] if files is None else files
    try:
        # Process the request data for constructing the chat state
        message: str = data.message.strip()  # orig vars overwritten on purpose
        api_key: str = data.api_key  # DocDocGo API key

        # If admin pwd is sent, use default key
        if (
            BYPASS_SETTINGS_RESTRICTIONS_PASSWORD
            and data.openai_api_key.strip() == BYPASS_SETTINGS_RESTRICTIONS_PASSWORD
        ):
            data.openai_api_key = DEFAULT_OPENAI_API_KEY

        openai_api_key: str = data.openai_api_key or DEFAULT_OPENAI_API_KEY

        # If BYPASS_SETTINGS_RESTRICTIONS is set, no key = use default key in *private* mode
        if (
            is_community_key := not data.openai_api_key
        ) and BYPASS_SETTINGS_RESTRICTIONS:
            data.openai_api_key = DEFAULT_OPENAI_API_KEY
            is_community_key = False

        user_id: str | None = get_short_user_id(data.openai_api_key)
        # TODO: use full api key as user id (but show only the short version)

        chat_history = convert_chat_history(data.chat_history)
        data.collection_name = data.collection_name or DEFAULT_COLLECTION_NAME
        collection_name = data.collection_name
        access_codes_cache: dict[str, str] | None = data.access_codes_cache
        if data.scheduled_queries_str is None:
            scheduled_queries = ScheduledQueries()
        else:
            # Decode from JSON string (encoded to have a simpler type in the frontend)
            scheduled_queries = ScheduledQueries.model_validate_json(
                data.scheduled_queries_str
            )

        # Validate the user's API key
        if api_key != os.getenv("DOCDOCGO_API_KEY"):
            print(f"Invalid API key: {api_key}")
            return ChatResponseData(content="Invalid API key.")

        # Validate the provided bot settings

        if data.bot_settings and is_community_key:
            # Enforce default settings for community key
            if data.bot_settings != BotSettings():
                return ChatResponseData(
                    content="Apologies, you can customize your model settings (e.g. model name, "
                    "temperature) only when using your own OpenAI API key."
                )

        # Extract text from the files and convert to list of Document
        docs, failed_files, unsupported_ext_files = extract_text(
            files, allow_all_ext=True
        )  # returns quickly if no files

        # Print and validate the user's message and successful upload
        if files:
            print(f"GOT {len(files)} FILES, {len(docs)} DOCUMENTS")
        if failed_files or unsupported_ext_files:
            return ChatResponseData(
                content=format_ingest_failure(failed_files, unsupported_ext_files)
            )

        # Parse the query (or get the next scheduled query if message/docs are empty)
        if message or docs:
            # If docs uploaded with empty message, interpret as "/upload"
            parsed_query = parse_query(message or "/upload")
        else:
            parsed_query = scheduled_queries.pop()
            if not parsed_query:
                return ChatResponseData(
                    content="Apologies, I received an empty message from you."
                )

        # If there are files but command is not ingest or summarize, postpone it till after ingestion
        if docs and parsed_query.chat_mode not in (
            ChatMode.INGEST_COMMAND_ID,
            ChatMode.SUMMARIZE_COMMAND_ID,
        ):
            scheduled_queries.add_to_front(parsed_query)
            parsed_query = parse_query("/upload")

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

        access_code_by_coll_by_user_id = (
            {user_id: access_codes_cache} if access_codes_cache else None
        )

        chat_state = ChatState(
            operation_mode=OperationMode.FASTAPI,
            vectorstore=vectorstore,
            is_community_key=is_community_key,
            chat_history=chat_history,
            chat_and_command_history=chat_history,  # no difference in this context
            openai_api_key=openai_api_key,
            user_id=user_id,
            parsed_query=parsed_query,
            scheduled_queries=scheduled_queries,
            access_code_by_coll_by_user_id=access_code_by_coll_by_user_id,
            uploaded_docs=docs,
            bot_settings=data.bot_settings,
        )

        # Validate (and cache, for this request) the user's access level
        access_role = get_access_role(chat_state)
        if access_role.value <= AccessRole.NONE.value:
            return ChatResponseData(
                content="Apologies, you do not have access to the collection."
            )

        # Get the bot's response
        result = get_bot_response(chat_state)
    except Exception as e:
        ic(traceback.format_exc())
        return ChatResponseData(
            content="Apologies, I encountered an error while trying to "
            f"compose a response to you. The error reads:\n\n{e}"
        )

    # print("AI:", reply) - no need, we are streaming to stdout now
    print(DELIMITER)

    # Determine the current collection name
    try:
        collection_name = result["vectorstore"].name
    except KeyError:
        pass

    # If result has instructions to auto-run a query, add to front of queue
    if new_parsed_query := result.get("new_parsed_query"):
        chat_state.scheduled_queries.add_to_front(new_parsed_query)

    # Prepare the response
    rsp = ChatResponseData(
        content=result["answer"],
        sources=get_source_links(result) or None,
        collection_name=collection_name,
        user_facing_collection_name=get_user_facing_collection_name(
            chat_state.user_id, collection_name
        ),
        instructions=result.get("instructions"),
        scheduled_queries_str=chat_state.scheduled_queries.model_dump_json()
        if chat_state.scheduled_queries
        else None,
    )

    # Return the response
    if rsp.sources:
        print("Sources:" + "\n".join(rsp.sources) + "\n" + DELIMITER)

    ic(rsp)
    return rsp


@app.get("/")
async def root():
    ic("/ endpoint hit: Hello from DocDocGo API!")
    return {"message": "Hello from DocDocGo API!"}


@app.get("/health/")
async def health():
    ic("/health/ endpoint hit: Hello from DocDocGo API!")
    return {"message": "Hello from DocDocGo API!"}


@app.post("/ingest/", response_model=ChatResponseData)
async def ingest(
    files: Annotated[list[UploadFile], File()],
    message: Annotated[str, Form()],
    api_key: Annotated[str, Form()],
    openai_api_key: Annotated[str | None, Form()] = None,
    chat_history: Annotated[str | None, Form()] = None,  # JSON string
    collection_name: Annotated[str | None, Form()] = None,
    access_codes_cache: Annotated[str | None, Form()] = None,  # JSON string
    scheduled_queries_str: Annotated[str | None, Form()] = None,
    bot_settings: Annotated[BotSettings | None, Form()] = None,
):
    """
    Handle a chat message from the user, which may include files, and return a
    response from the bot.
    """
    ic("Ingest endpoint hit")
    # Validate the total size of the files
    total_size = 0

    for ufile in files:
        # Move to the end of the file and get the position
        ufile.file.seek(0, 2)  # Seek to the end
        total_size += ufile.file.tell()  # Position = size
        ufile.file.seek(0)  # Reset for any further operations

    if total_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"The total size of the files exceeds the permitted limit of {MAX_UPLOAD_BYTES} bytes.",
        )

    # Apparently if Upload is clicked in the browser with no file selected,
    # then 'files' will NOT be empty, but will contain 1 file with no bytes.
    if total_size == 0:
        files = []

    # We need to decode the parameters from the form data because they are JSON strings
    # or None. In particular, I made it so that even string fields are expected to be encoded.
    # One reason for this is that passing an empty string in a form field causes a 422 error.
    # The problem is solved if we encode all strings - then an empty string becomes '""'.
    try:
        # Decode and validate request data
        data = ChatRequestData(
            message=decode_param(message),
            api_key=decode_param(api_key),
            openai_api_key=decode_param(openai_api_key),
            chat_history=decode_param(chat_history),
            collection_name=decode_param(collection_name),
            access_codes_cache=decode_param(access_codes_cache),
            scheduled_queries_str=decode_param(scheduled_queries_str),
        )
        ic(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {e}")

    return await handle_chat_or_ingest_request(data, files)


@app.post("/chat/", response_model=ChatResponseData)
async def chat(data: ChatRequestData = Body(...)):
    """Handle a chat message from the user and return a response from the bot"""
    ic("Chat endpoint hit")
    return await handle_chat_or_ingest_request(data)


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
