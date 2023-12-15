import os
import random

import streamlit as st

from components.llm import CallbackHandlerDDGStreamlit
from docdocgo import get_bot_response
from utils.helpers import DELIMITER, extract_chat_mode_from_query, parse_query
from utils.streamlit.helpers import status_config
from utils.streamlit.prepare import prepare_app
from utils.type_utils import ChatState

# Run just once
if "chat_state" not in st.session_state:
    prepare_app()

# For convenience
chat_state: ChatState = st.session_state.chat_state

# Page config
icons = "🤖🦉🦜🦆🐦🕊️🦩"
page_icon = random.choice(icons)
st.set_page_config(page_title="DocDocGo", page_icon=page_icon)
st.title("DocDocGo")

# Sidebar
with st.sidebar:
    # Set the env variable for the OpenAI API key.
    # Init value of text field is determined by the init value of the env variable.
    did_chat_succeed = not chat_state.chat_history
    with st.expander("OpenAI API Key", expanded=did_chat_succeed):
        os.environ["OPENAI_API_KEY"] = st.text_input(
            "OpenAI API Key",
            label_visibility="collapsed",
            value=st.session_state.openai_api_key_field_init_value,
            key="openai_api_key",
            type="password",
        )
        
        "To use this app, you'll need an OpenAI API key."
        "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
    "[View the source code](https://github.com/reasonmethis/docdocgo-core/streamlit_app.py)"

# Show previous exchanges
for full_query, answer in chat_state.chat_and_command_history:
    with st.chat_message("user"):
        st.markdown(full_query)
    with st.chat_message("assistant"):
        st.markdown(answer)

# Check if the user has entered a query
if not (full_query := st.chat_input("What's on your mind?")):
    st.stop()

#### The rest will only once the user has entered a query ####

with st.chat_message("user"):
    st.markdown(full_query)

# Parse the query to extract command id & search params, if any
query, chat_mode = extract_chat_mode_from_query(full_query)
query, search_params = parse_query(query)
chat_state.update(chat_mode=chat_mode, message=query, search_params=search_params)

# Get and display response from the bot
with st.chat_message("assistant"):
    try:
        status = st.status(status_config[chat_mode]["thinking.header"])
        status.write(status_config[chat_mode]["thinking.body"])
    except KeyError:
        status = None
    message_placeholder = st.empty()
    callback_handler = CallbackHandlerDDGStreamlit(message_placeholder)
    chat_state.callbacks[1] = callback_handler
    try:
        response = get_bot_response(chat_state)
        if status:
            status.update(
                label=status_config[chat_mode]["complete.header"], state="complete"
            )
            status.write(status_config[chat_mode]["complete.body"])

        answer = response["answer"]
        if not response.get("skip_chat_history", False):
            chat_state.chat_history.append((query, answer))
    except Exception as e:
        if status:
            status.update(label=status_config[chat_mode]["error.header"], state="error")
            status.write(status_config[chat_mode]["error.body"])

        answer = f"Apologies, an error has occurred:\n```\n{e}\n```"
        print(f"{answer}\n{DELIMITER}")

        if callback_handler.buffer:
            answer = f"{callback_handler.buffer}\n\n{answer}"
        if os.getenv("RERAISE_EXCEPTIONS"):
            raise e
        st.stop()
    finally:
        message_placeholder.markdown(answer)
        chat_state.chat_and_command_history.append((full_query, answer))

# Update iterative research data
if "ws_data" in response:
    chat_state.ws_data = response["ws_data"]
# TODO: update in flask app as well

# Update vectorstore if needed
if "vectorstore" in response:
    chat_state.vectorstore = response["vectorstore"]

# If this was the first exchange, rerun to collapse the OpenAI API key field
if len(chat_state.chat_history) == 1:
    st.rerun()