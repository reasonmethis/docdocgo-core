import os

import streamlit as st

from components.llm import CallbackHandlerDDGConsole
from docdocgo import do_intro_tasks
from utils.chat_state import ChatState
from utils.prepare import OPENAI_API_KEY, DEFAULT_OPENROUTER_API_KEY, DUMMY_OPENROUTER_API_KEY_PLACEHOLDER, MODEL_NAME
from utils.streamlit.fix_event_loop import remove_tornado_fix
from utils.type_utils import OperationMode
from utils.streamlit.helpers import mode_options


def prepare_app():
    if os.getenv("STREAMLIT_SCHEDULED_MAINTENANCE"):
        st.markdown("Welcome to DocDocGo! 🦉")
        st.markdown(
            "Scheduled maintenance is currently in progress. Please check back later."
        )
        st.stop()

    # Flag for whether or not the OpenRouter and OpenAI API keys have succeeded at least once
    st.session_state.llm_api_key_ok_status = False
    st.session_state.openrouter_api_key_ok_status = False

    print("query params:", st.query_params)
    st.session_state.update_query_params = None
    st.session_state.init_collection_name = st.query_params.get("collection")
    st.session_state.access_code = st.query_params.get("access_code")
    try:
        remove_tornado_fix()
        vectorstore = do_intro_tasks(openai_api_key=OPENAI_API_KEY)
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
        openrouter_api_key=DEFAULT_OPENROUTER_API_KEY,
        openai_api_key=OPENAI_API_KEY,
    )

    st.session_state.prev_supplied_openai_api_key = None
    st.session_state.prev_supplied_openrouter_api_key = None
    st.session_state.openai_api_key = OPENAI_API_KEY
    st.session_state.default_openrouter_api_key = DEFAULT_OPENROUTER_API_KEY
    if st.session_state.default_openrouter_api_key == DUMMY_OPENROUTER_API_KEY_PLACEHOLDER:
        st.session_state.default_openrouter_api_key = ""

    st.session_state.model = MODEL_NAME

    st.session_state.idx_file_upload = -1
    st.session_state.uploader_form_key = "uploader-form"

    st.session_state.idx_file_download = -1
    st.session_state.downloader_form_key = "downloader"

    st.session_state.user_avatar = os.getenv("USER_AVATAR") or None
    st.session_state.bot_avatar = os.getenv("BOT_AVATAR") or None  # TODO: document this

    SAMPLE_QUERIES = os.getenv(
        "SAMPLE_QUERIES",
        "/research heatseek Code for row of buttons Streamlit, /research What are the biggest AI news this month?, /help How does infinite research work?",
    )
    st.session_state.sample_queries = [q.strip() for q in SAMPLE_QUERIES.split(",")]
    st.session_state.default_mode = mode_options[0]