import os

import streamlit as st

from components.llm import CallbackHandlerDDGConsole
from docdocgo import do_intro_tasks
from utils.chat_state import ChatState
from utils.prepare import DUMMY_OPENAI_API_KEY_PLACEHOLDER
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.type_utils import OperationMode


def prepare_app():
    if os.getenv("STREAMLIT_SCHEDULED_MAINTENANCE"):
        st.markdown("Welcome to DocDocGo! 🦉")
        st.markdown("Scheduled maintenance is currently in progress. Please check back later.")
        st.stop()

    # Flag for whether or not the OpenAI API key has succeeded at least once
    st.session_state.llm_api_key_ok_status = False

    print("query params:", st.query_params)
    st.session_state.update_query_params = None
    st.session_state.init_collection_name = st.query_params.get("collection")
    st.session_state.access_code = st.query_params.get("access_code")
    DEFAULT_OPENAI_API_KEY = os.getenv("DEFAULT_OPENAI_API_KEY")
    try:
        remove_tornado_fix()
        vectorstore = do_intro_tasks(openai_api_key=DEFAULT_OPENAI_API_KEY)
    except Exception as e:
        st.error(
            "Apologies, I could not load the vector database. This "
            "could be due to a misconfiguration of the environment variables "
            f"or missing files. The error reads: \n\n{e}"
        )
        st.stop()

    st.session_state.chat_state = ChatState(
        operation_mode=OperationMode.STREAMLIT,
        vectorstore=vectorstore,
        callbacks=[
            CallbackHandlerDDGConsole(),
            "placeholder for CallbackHandlerDDGStreamlit",
        ],
        openai_api_key=DEFAULT_OPENAI_API_KEY,
    )

    st.session_state.prev_supplied_openai_api_key = None
    st.session_state.default_openai_api_key = DEFAULT_OPENAI_API_KEY or ""
    if st.session_state.default_openai_api_key == DUMMY_OPENAI_API_KEY_PLACEHOLDER:
        st.session_state.default_openai_api_key = ""

    st.session_state.idx_file_upload = -1
    st.session_state.uploader_form_key = "uploader-form"

    st.session_state.user_avatar = os.getenv("USER_AVATAR") or None
    st.session_state.bot_avatar = os.getenv("BOT_AVATAR") or None
