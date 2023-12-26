import os

import streamlit as st

from components.llm import CallbackHandlerDDGConsole
from docdocgo import do_intro_tasks
from utils.chat_state import ChatState
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.type_utils import OperationMode


def prepare_app():
    st.session_state.openai_api_key_init_value = os.getenv("OPENAI_API_KEY", "")

    # Usually start with settings restrictions, user can unlock by entering pwd or OpenAI key
    st.session_state.allow_all_settings_for_default_key = bool(
        os.getenv("BYPASS_SETTINGS_RESTRICTIONS")
    )

    # Whether or not the OpenAI API key has succeeded at least once
    st.session_state.llm_api_key_ok_status = False

    try:
        remove_tornado_fix()  # used to be run on every rerun
        vectorstore = do_intro_tasks()
    except Exception as e:
        st.error(
            "Apologies, I could not load the vector database. This "
            "could be due to a misconfiguration of the environment variables "
            f"or missing file. The error reads: \n\n{e}"
        )
        st.stop()

    st.session_state.chat_state = ChatState(
        OperationMode.STREAMLIT,
        vectorstore=vectorstore,
        callbacks=[
            CallbackHandlerDDGConsole(),
            "placeholder for CallbackHandlerDDGStreamlit",
        ],
    )
