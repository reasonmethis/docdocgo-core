import os
import random

import streamlit as st

from components.llm import CallbackHandlerDDGConsole, CallbackHandlerDDGStreamlit
from docdocgo import do_intro_tasks, get_bot_response
from utils.helpers import DELIMITER, extract_chat_mode_from_query, parse_query
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.streamlit.helpers import status_config
from utils.type_utils import ChatState, OperationMode

remove_tornado_fix()

# Run just once
if "chat_state" not in st.session_state:
    st.session_state.vectorstore = do_intro_tasks()
    st.session_state.chat_state = ChatState(
        OperationMode.STREAMLIT,
        vectorstore=st.session_state.vectorstore,
        callbacks=[
            CallbackHandlerDDGConsole(),
            "placeholder for CallbackHandlerDDGStreamlit",
        ],
    )

chat_state: ChatState = st.session_state.chat_state

icons = "🤖🦉🦚🦜🦆🦢🦅🐧🐦🐤🐔🐓🕊️🦩🦋🐝🐞"
page_icon = random.choice(icons)

st.set_page_config(page_title="DocDocGo", page_icon=page_icon)
st.title("DocDocGo")

for full_query, answer in chat_state.chat_and_command_history:
    with st.chat_message("user"):
        st.markdown(full_query)
    with st.chat_message("assistant"):
        st.markdown(answer)

if not (full_query := st.chat_input("What's on your mind?")):
    st.stop()

with st.chat_message("user"):
    st.markdown(full_query)

# Parse the query to extract command id & search params, if any
query, chat_mode = extract_chat_mode_from_query(full_query)
query, search_params = parse_query(query)
chat_state.update(command_id=chat_mode, message=query, search_params=search_params)

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
