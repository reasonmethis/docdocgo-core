"""
The flask server that enables API access to DocDocGo.
NOTE: The logic below needs to be updated to catch up with the latest features in
docdocgo.py. Specifically, we need to add support for the /db command and the
/research command.
"""

import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from _prepare_env import is_env_loaded
from agents.dbmanager import get_access_role, get_short_user_id
from components.chroma_ddg import load_vectorstore
from docdocgo import get_bot_response, get_source_links
from utils.chat_state import ChatState
from utils.helpers import DELIMITER
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.query_parsing import parse_query
from utils.type_utils import AccessRole, JSONish, OperationMode, PairwiseChatHistory

app = Flask(__name__)

# Allow all domains/origins
CORS(app)

# Or, for more granular control, specify domains:
# CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})

is_env_loaded = is_env_loaded  # see explanation at the end of docdocgo.py


def convert_chat_history(
    chat_history_in_role_format: list[JSONish],
) -> PairwiseChatHistory:
    """Converts the chat history into a list of tuples of the form (user_message, bot_message)"""

    chat_history = []
    user_message = ""
    for chat in chat_history_in_role_format:
        if chat["role"] == "user":
            user_message = chat["content"]
        elif chat["role"] == "assistant":
            chat_history.append((user_message, chat["content"]))
            user_message = ""
    return chat_history


def format_simple_response(msg: str):
    return jsonify({"content": msg})


@app.route("/chat", methods=["POST"])
def chat():
    """Handles a chat message from the user and returns a response from the bot"""
    try:
        DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY")

        # Get the user's message and other info from the request
        data = request.json
        message = data["message"].strip()

        api_key = data["api_key"]  # DocDocGo API key
        openai_api_key = data.get("openai_api_key", DEFAULT_OPENAI_API_KEY)
        user_id = get_short_user_id(openai_api_key)
        # TODO: use full api key as user id (but show only the short version)

        chat_history = convert_chat_history(data["chat_history"])
        collection_name = data.get("collection", DEFAULT_COLLECTION_NAME)
        access_code = data.get("access_code")

        # Validate the user's API key
        if api_key != os.getenv("DOCDOCGO_API_KEY"):
            print(f"Invalid API key: {api_key}")
            return format_simple_response("Invalid API key")

        # Parse the query
        parsed_query = parse_query(message)

        # Initialize vectorstore and chat state
        try:
            vectorstore = load_vectorstore(
                collection_name, openai_api_key=openai_api_key
            )
        except Exception as e:
            return format_simple_response(
                "Apologies, I could not load the vector database. This "
                "could be due to a misconfiguration of the environment variables "
                f"or missing files. The error reads: \n\n{e}"
            )
        chat_state = ChatState(
            operation_mode=OperationMode.FLASK,
            vectorstore=vectorstore,
            chat_history=chat_history,
            chat_and_command_history=chat_history,  # not used in flask mode
            openai_api_key=openai_api_key,
            user_id=user_id,
            parsed_query=parsed_query,
        )

        # Validate (and cache, for this request) the user's access level
        access_role = get_access_role(chat_state, None, access_code)
        if access_role.value <= AccessRole.NONE.value:
            return format_simple_response(
                "Apologies, you do not have access to the collection."
            )

        # Print and validate the user's message
        print(f"GOT MESSAGE FROM {user_id}:\n{message}")
        if not message:
            return format_simple_response(
                "Apologies, I received an empty message from you."
            )

        # Get the bot's response
        result = get_bot_response(chat_state)

        # Get the reply and sources from the bot's response
        reply = result["answer"]
        source_links = get_source_links(result)
    except Exception as e:
        print(e)
        return format_simple_response(
            "Apologies, I encountered an error while trying to "
            f"compose a response to you. The error reads:\n\n{e}"
        )

    # Print and form the response
    # print("AI:", reply) - no need, we are streaming to stdout now
    print(DELIMITER)
    if source_links:
        print("Sources:" + "\n".join(source_links) + DELIMITER)

    rsp = {"content": reply, "sources": source_links}

    # If collection was changed, return the new collection name
    try:
        rsp["collection_name"] = result["vectorstore"].collection_name
    except KeyError:
        pass

    # Return the response
    return jsonify(rsp)


if __name__ == "__main__":
    # print("Please run the server using waitress or gunicorn instead.")
    app.run(host="0.0.0.0", debug=True)  # listening on all public IPs
