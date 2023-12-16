import os

import streamlit as st

from components.llm import CallbackHandlerDDGConsole
from docdocgo import do_intro_tasks
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.type_utils import ChatState, OperationMode


def prepare_app():
    st.session_state.openai_api_key_field_init_value = os.getenv("OPENAI_API_KEY", "")
    st.session_state.llm_api_key_ok_status = False
    try:
        remove_tornado_fix()  # used to be run on every rerun
        st.session_state.vectorstore = do_intro_tasks()
    except Exception as e:
        st.error(
            "Apologies, I could not load the vector database. This "
            "could be due to a misconfiguration of the environment variables "
            f"or missing file. The error reads: \n\n{e}"
        )
        st.stop()

    st.session_state.chat_state = ChatState(
        OperationMode.STREAMLIT,
        vectorstore=st.session_state.vectorstore,
        callbacks=[
            CallbackHandlerDDGConsole(),
            "placeholder for CallbackHandlerDDGStreamlit",
        ],
    )
