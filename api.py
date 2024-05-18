"""
The FastAPI server that enables API access to DocDocGo.
"""

import json
import os
import traceback
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
from components.chroma_ddg import get_vectorstore_using_openai_api_key
from docdocgo import get_bot_response, get_source_links
from utils.chat_state import AgentDataDict, ChatState, ScheduledQueries
from utils.helpers import DELIMITER
from utils.ingest import extract_text, format_ingest_failure
from utils.prepare import (
    BYPASS_SETTINGS_RESTRICTIONS,
    BYPASS_SETTINGS_RESTRICTIONS_PASSWORD,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_OPENAI_API_KEY,
    INCLUDE_ERROR_IN_USER_FACING_ERROR_MSG,
    MAX_UPLOAD_BYTES,
    get_logger,
)
from utils.query_parsing import parse_query
from utils.type_utils import (
    INSTRUCT_AUTO_RUN_NEXT_QUERY,
    AccessRole,
    BotSettings,
    ChatMode,
    DDGError,
    Instruction,
    OperationMode,
    PairwiseChatHistory,
)

logger = get_logger()

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
RoleBasedChatMessage = dict[str, str]  # {"role": "user" | "assistant", "content": str}


class ChatRequestData(BaseModel):
    message: str
    api_key: str
    openai_api_key: str | None = None
    chat_history: list[RoleBasedChatMessage] = []
    collection_name: str | None = None
    access_codes_cache: dict[str, str] | None = None  # coll name -> access_code
    agentic_flow_state_str: str | None = None  # JSON string that frontend passes back
    bot_settings: BotSettings | None = None

    def parse_agentic_state(self):
        agentic_state: dict = json.loads(self.agentic_flow_state_str or "{}")

        if (tmp := agentic_state.get("scheduled_queries")) is None:
            scheduled_queries = ScheduledQueries()
        else:
            scheduled_queries = ScheduledQueries.model_validate_json(tmp)

        agent_data: AgentDataDict = agentic_state.get("agent_data", {})
        # TODO: validate agent_data

        return scheduled_queries, agent_data


class ChatResponseData(BaseModel):
    content: str
    sources: list[str] | None = None
    collection_name: str | None = None
    user_facing_collection_name: str | None = None
    instructions: list[Instruction] | None = None
    agentic_flow_state_str: str | None = None  # JSON string that frontend passes back

    @staticmethod
    def encode_agentic_state(
        scheduled_queries: ScheduledQueries, agent_data: AgentDataDict
    ):
        return json.dumps(
            {
                "scheduled_queries": scheduled_queries.model_dump_json(),
                "agent_data": agent_data,
            }
        )


def convert_chat_history(
    chat_history_in_role_format: list[RoleBasedChatMessage],
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
    data: ChatRequestData, files: list[UploadFile] = []
):
    try:
        # Process the request data for constructing the chat state
        message = data.message.strip()
        api_key = data.api_key  # DocDocGo API key

        # If admin pwd is sent, treat it as if the default key was sent
        if (
            BYPASS_SETTINGS_RESTRICTIONS_PASSWORD
            and data.openai_api_key
            and data.openai_api_key.strip() == BYPASS_SETTINGS_RESTRICTIONS_PASSWORD
            and DEFAULT_OPENAI_API_KEY # only do this if the default key is configured
        ):
            data.openai_api_key = DEFAULT_OPENAI_API_KEY
        # Same story if no key is sent but BYPASS_SETTINGS_RESTRICTIONS is set
        elif not data.openai_api_key and BYPASS_SETTINGS_RESTRICTIONS:
            data.openai_api_key = DEFAULT_OPENAI_API_KEY

        # If no key is specified, use the default key (but set is_community_key to True)
        openai_api_key: str = data.openai_api_key or DEFAULT_OPENAI_API_KEY
        is_community_key = not data.openai_api_key

        # User id is determined from the OpenAI API key (or None if community key)
        user_id: str | None = get_short_user_id(data.openai_api_key)
        # TODO: use full api key as user id (but show only the short version)

        chat_history = convert_chat_history(data.chat_history)
        data.collection_name = data.collection_name or DEFAULT_COLLECTION_NAME
        collection_name = data.collection_name
        access_codes_cache: dict[str, str] | None = data.access_codes_cache

        scheduled_queries, agent_data = data.parse_agentic_state()

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
            vectorstore = get_vectorstore_using_openai_api_key(
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
            openai_api_key=openai_api_key,
            user_id=user_id,
            parsed_query=parsed_query,
            scheduled_queries=scheduled_queries,
            agent_data=agent_data,
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
    except DDGError as e:
        print(traceback.format_exc())
        user_msg = (
            e.user_facing_message_full
            if INCLUDE_ERROR_IN_USER_FACING_ERROR_MSG
            else e.user_facing_message
        )
        print("User message:", user_msg)
        return ChatResponseData(content=user_msg)  # NOTE: think about http status codes
    except Exception:
        print(traceback.format_exc())

        return ChatResponseData(
            content="Apologies, I encountered an error while trying to "
            "compose a response to you."
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
        chat_state.scheduled_queries.add_to_front(new_parsed_query)  # should move this

    # If needed, add an explicit instruction to auto-run a query
    instructions: list | None = result.get("instructions")
    if chat_state.scheduled_queries:
        instructions = instructions or []
        instructions.append(Instruction(type=INSTRUCT_AUTO_RUN_NEXT_QUERY))
        # NOTE: may want to move this to the main engine

    # Prepare the response
    rsp = ChatResponseData(
        content=result["answer"],
        sources=get_source_links(result) or None,
        collection_name=collection_name,
        user_facing_collection_name=get_user_facing_collection_name(
            chat_state.user_id, collection_name
        ),
        instructions=instructions,
        agentic_flow_state_str=ChatResponseData.encode_agentic_state(
            chat_state.scheduled_queries, chat_state.agent_data
        ),
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
    agent_data: Annotated[str | None, Form()] = None,  # JSON string
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
            agentic_flow_state_str=decode_param(scheduled_queries_str),
            bot_settings=decode_param(bot_settings),
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
