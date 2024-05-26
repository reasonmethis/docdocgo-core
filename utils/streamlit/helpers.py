import re
import time
from typing import Any

import streamlit as st
from pydantic import BaseModel

from utils.type_utils import ChatMode

WELCOME_TEMPLATE_COLL_IN_URL = """\
Welcome! You are now using the `{}` collection. \
When chatting, I will use its content as my knowledge base. \
To get help using me, just type `/help <your question>`.\
"""

NO_AUTH_TEMPLATE_COLL_IN_URL = """\
Apologies, the current URL doesn't provide access to the \
requested collection `{}`. This can happen if the \
access code is invalid or if the collection doesn't exist.
                            
I have switched to my default collection.

To get help using me, just type `/help <your question>`.\
"""

WELCOME_MSG_NEW_CREDENTIALS = """\
Welcome! The user credentials have changed but you are still \
authorised for the current collection.\
"""

NO_AUTH_MSG_NEW_CREDENTIALS = """\
Welcome! The user credentials have changed, \
so I've switched to the default collection.\
"""

POST_INGEST_MESSAGE_TEMPLATE_NEW_COLL = """\
Your documents have been uploaded to a new collection: `{coll_name}`. \
You can now use this collection in your queries. If you are done uploading, \
you can rename it:
```
/db rename my-cool-collection-name
```
"""

POST_INGEST_MESSAGE_TEMPLATE_EXISTING_COLL = """\
Your documents have been added to the existing collection: `{coll_name}`. \
If you are done uploading, you can rename it:
```
/db rename my-cool-collection-name
```
"""

chat_with_docs_status_config = {
    "thinking.header": "One sec...",
    "thinking.body": "Retrieving sources and composing reply...",
    "complete.header": "Done!",
    "complete.body": "Reply composed.",
    "error.header": "Error.",
    "error.body": "Apologies, there was an error.",
}

just_chat_status_config = chat_with_docs_status_config | {
    "thinking.body": "Composing reply...",
}

web_status_config = chat_with_docs_status_config | {
    "thinking.header": "Doing Internet research (takes 10-30s)...",
    "thinking.body": "Retrieving content from websites and composing report...",
    "complete.body": "Report composed.",
}

research_status_config = chat_with_docs_status_config | {
    "thinking.header": "Doing Internet research (takes 10-30s)...",
    "thinking.body": "Retrieving content from websites and composing report...",
    "complete.body": "Report composed and sources added to the document collection.",
}

ingest_status_config = chat_with_docs_status_config | {
    "thinking.header": "Ingesting...",
    "thinking.body": "Retrieving and ingesting content...",
    "complete.body": "Content was added to the document collection.",
}

summarize_status_config = chat_with_docs_status_config | {
    "thinking.header": "Summarizing and ingesting...",
    "thinking.body": "Retrieving, summarizing, and ingesting content...",
    "complete.body": "Summary composed and retrieved content added to the document collection.",
}

status_config = {
    ChatMode.JUST_CHAT_COMMAND_ID: just_chat_status_config,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID: chat_with_docs_status_config,
    ChatMode.DETAILS_COMMAND_ID: chat_with_docs_status_config,
    ChatMode.QUOTES_COMMAND_ID: chat_with_docs_status_config,
    ChatMode.HELP_COMMAND_ID: chat_with_docs_status_config,
    ChatMode.WEB_COMMAND_ID: web_status_config,
    ChatMode.RESEARCH_COMMAND_ID: research_status_config,
    ChatMode.INGEST_COMMAND_ID: ingest_status_config,
    ChatMode.SUMMARIZE_COMMAND_ID: summarize_status_config,
}

STAND_BY_FOR_INGESTION_MESSAGE = (
    "\n\n--- \n\n> **PLEASE STAND BY WHILE CONTENT IS INGESTED...**"
)


def get_init_msg(is_initial_load, is_authorised, coll_name_in_url, init_coll_name):
    if not is_initial_load:  # key changed without reloading the page
        if is_authorised:
            return WELCOME_MSG_NEW_CREDENTIALS
        else:
            return NO_AUTH_MSG_NEW_CREDENTIALS
    elif coll_name_in_url:  # page (re)load with coll in URL
        if is_authorised:
            return WELCOME_TEMPLATE_COLL_IN_URL.format(init_coll_name)
        else:
            return NO_AUTH_TEMPLATE_COLL_IN_URL.format(init_coll_name)
    else:  # page (re)load without coll in URL
        return None  # just to be explicit


def update_url(params: dict[str, str]):
    st.query_params.clear()  # NOTE: should be a way to set them in one go
    st.query_params.update(params)


def update_url_if_scheduled():
    if st.session_state.update_query_params is not None:
        update_url(st.session_state.update_query_params)
        st.session_state.update_query_params = None


def escape_dollars(text: str) -> str:
    """
    Escape dollar signs in the text that come before numbers.
    """
    return re.sub(r"\$(?=\d)", r"\$", text)


def fix_markdown(text: str) -> str:
    """
    Escape dollar signs in the text that come before numbers and add
    two spaces before every newline.
    """
    return re.sub(r"\$(?=\d)", r"\$", text).replace("\n", "  \n")


def write_slowly(message_placeholder, answer, delay=None):
    """Write a message to the message placeholder not all at once but word by word."""
    pieces = answer.split(" ")
    delay = delay or min(0.025, 10 / (len(pieces) + 1))
    for i in range(1, len(pieces) + 1):
        message_placeholder.markdown(fix_markdown(" ".join(pieces[:i])))
        time.sleep(delay)


def show_sources(
    sources: list[str] | None,
    callback_handler=None,
):
    """Show the sources if present."""
    # If the cb handler is provided, remove the stand-by message
    if callback_handler and callback_handler.end_str_printed:
        callback_handler.container.markdown(fix_markdown(callback_handler.buffer))

    if not sources:
        return
    with st.expander("Sources"):
        for source in sources:
            st.markdown(source)


def show_uploader(is_teleporting=False, border=True):
    if is_teleporting:
        try:
            st.session_state.uploader_placeholder.empty()
        except AttributeError:
            pass  # should never happen, but just in case
        # Switch between one of the two possible keys (to avoid duplicate key error)
        st.session_state.uploader_form_key = (
            "uploader-form-alt"
            if st.session_state.uploader_form_key == "uploader-form"
            else "uploader-form"
        )

    # Show the uploader
    st.session_state.uploader_placeholder = st.empty()
    with st.session_state.uploader_placeholder:
        with st.form(
            st.session_state.uploader_form_key, clear_on_submit=True, border=border
        ):
            files = st.file_uploader(
                "Upload your documents",
                accept_multiple_files=True,
                label_visibility="collapsed",
            )
            cols = st.columns([1, 1])
            with cols[0]:
                is_submitted = st.form_submit_button("Upload")
            with cols[1]:
                allow_all_ext = st.toggle("Allow all extensions", value=False)
    return (files if is_submitted else []), allow_all_ext


class DownloaderData(BaseModel):
    data: Any
    file_name: str
    mime: str = "text/plain"


def show_downloader(
    downloader_data: DownloaderData | None = None, is_teleporting=False
):
    if downloader_data is None:
        try:
            # Use the data from the already existing downloader
            downloader_data = st.session_state.downloader_data
        except AttributeError:
            raise ValueError("downloader_data not provided and not in session state")
    else:
        st.session_state.downloader_data = downloader_data

    if is_teleporting:
        try:
            st.session_state.downloader_placeholder.empty()
        except AttributeError:
            pass  # should never happen, but just in case

        # Switch between one of the two possible keys (to avoid duplicate key error)
        st.session_state.downloader_form_key = (
            "downloader-alt"
            if st.session_state.downloader_form_key == "downloader"
            else "downloader"
        )

    # Show the downloader
    st.session_state.downloader_placeholder = st.empty()
    with st.session_state.downloader_placeholder:
        is_downloaded = st.download_button(
            label="Download Exported Data",
            data=downloader_data.data,
            file_name=downloader_data.file_name,
            mime=downloader_data.mime,
            key=st.session_state.downloader_form_key,
        )
    return is_downloaded
