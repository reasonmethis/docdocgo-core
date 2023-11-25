""" The flask server that enables API access to DocDocGo. """
from collections import defaultdict
import os
import json
from flask import Flask, jsonify, request

from utils.type_utils import JSONish, PairwiseChatHistory
from docdocgo import get_bot_response, get_source_links
from utils.helpers import DELIMITER, parse_query

app = Flask(__name__)

prev_input_by_user = defaultdict(dict)
prev_outputs = defaultdict(dict)


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


@app.route("/chat", methods=["POST"])
def chat():
    """Handles a chat message from the user and returns a response from the bot"""
    try:
        # Get the user's message from the request
        data = request.json
        username = data["username"]
        message = data["message"]
        command_id = data["command_id"]
        api_key = data["api_key"]
        chat_history = convert_chat_history(data["chat_history"])

        # Validate the user's API key
        if api_key != os.getenv("DOCDOCGO_API_KEY"):
            print(f"Invalid API key: {api_key}")
            return jsonify({"content": "Invalid DocDocGo API key"})

        # Parse the query to extract search params, if any
        message, search_params = parse_query(message)

        # Process commands that don't require a response from the bot
        if command_id == 4:  # /retry command
            return jsonify(
                {
                    "prev_user_msg": prev_input_by_user[username].get("message", ""),
                    "prev_command_id": prev_input_by_user[username].get(
                        "command_id", -1
                    ),
                    "prev_search_params": prev_input_by_user[username].get(
                        "search_params", {}
                    ),
                    "content": prev_outputs[username].get("content", ""),
                    "sources": prev_outputs[username].get("sources", ""),
                }
            )

        # Save the user's message (for the /retry command; will save response later)
        prev_input_by_user[username] = {
            "message": message,
            "command_id": command_id,
            "search_params": search_params,
        }

        # Print and validate the user's message
        print(f"GOT MESSAGE FROM {username} with cmd id {command_id}:\n{message}")
        if search_params:
            print("\nSEARCH PARAMS:")
            print(json.dumps(search_params, indent=4))
        print(DELIMITER)

        if not message:
            prev_outputs[username] = {
                "content": f"Apologies {username}, I received an empty message from you."
            }
            return jsonify(prev_outputs[username])

        # Initialize the chain with the right settings and get the bot's response
        result = get_bot_response(message, chat_history, search_params, command_id)

        # Get the reply and sources from the bot's response
        reply = result["answer"]
        source_links = get_source_links(result)
    except Exception as e:
        print(e)
        # Save the response we are about to return, then return it
        prev_outputs[username] = {
            "content": f"{username}, I am sorry, I encountered an error while trying to "
            f"compose a response to you. The error reads:\n\n{e}",
        }
        return jsonify(prev_outputs[username])

    # Print and return the response
    print()  # ("AI:", reply) - no need, we are streaming to stdout now
    print(DELIMITER)
    print("Sources:")
    print("\n".join(source_links))
    print(DELIMITER)

    prev_outputs[username] = {"content": reply, "sources": source_links}
    return jsonify(prev_outputs[username])


if __name__ == "__main__":
    print("Please run the server using waitress or gunicorn instead.")
    # app.run(host="0.0.0.0", debug=True)  # listening on all public IPs
