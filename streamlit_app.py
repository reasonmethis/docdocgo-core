import os
import streamlit as st
from components.llm import CallbackHandlerDDGConsole, CallbackHandlerDDGStreamlit
from docdocgo import do_intro_tasks, get_bot_response
from utils.helpers import DELIMITER, extract_command_id_from_query, parse_query
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.type_utils import ChatState


remove_tornado_fix()

# Run just once
if "chat_state" not in st.session_state:
    st.session_state.vectorstore = do_intro_tasks()
    st.session_state.chat_state = ChatState(
        -1,
        vectorstore=st.session_state.vectorstore,
        callbacks=[
            CallbackHandlerDDGConsole(),
            "placeholder for CallbackHandlerDDGStreamlit",
        ],
    )

chat_state = st.session_state.chat_state

st.title("DocDocGo")

for query, answer in chat_state.chat_history:
    with st.chat_message("user"):
        st.markdown(query)
    with st.chat_message("assistant"):
        st.markdown(answer)

if not (query := st.chat_input("What's on your mind?")):
    st.stop()

with st.chat_message("user"):
    st.markdown(query)

# Parse the query to extract command id & search params, if any
query, command_id = extract_command_id_from_query(query)
query, search_params = parse_query(query)
chat_state.update(command_id=command_id, message=query, search_params=search_params)

with st.chat_message("assistant"):
    message_placeholder = st.empty()
    chat_state.callbacks[1] = CallbackHandlerDDGStreamlit(message_placeholder)
    try:
        response = get_bot_response(chat_state)
        answer = response["answer"]
        # message_placeholder.markdown(answer)
        if answer:
            chat_state.chat_history.append((query, answer))
    except Exception as e:
        print("<Apologies, an error has occurred>")
        print("ERROR:", e)
        print(DELIMITER)
        if os.getenv("RERAISE_EXCEPTIONS"):
            raise e
        st.stop()

    # Update iterative research data
    if "ws_data" in response:
        chat_state.ws_data = response["ws_data"]
    # TODO: update in API as well

    # Update vectorstore if needed
    if "vectorstore" in response:
        chat_state.vectorstore = response["vectorstore"]