import time
import streamlit as st
from utils.type_utils import ChatMode

default_status_config = {
    "thinking.header": "One sec...",
    "thinking.body": "Retrieving sources and composing reply.",
    "complete.header": "Done!",
    "complete.body": "Reply composed.",
    "error.header": "Error.",
    "error.body": "Apologies, an error has occurred.",
}

just_chat_status_config = default_status_config | {
    "thinking.body": "Composing reply...",
}

research_status_config = default_status_config | {
    "thinking.header": "Doing Internet research (takes 10-30s)...",
    "thinking.body": "Retrieving content from websites and composing report...",
    "complete.body": "Report composed and sources added to the document collection.",
}

status_config = {
    ChatMode.JUST_CHAT_COMMAND_ID: just_chat_status_config,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID: default_status_config,
    ChatMode.DETAILS_COMMAND_ID: default_status_config,
    ChatMode.QUOTES_COMMAND_ID: default_status_config,
    ChatMode.WEB_COMMAND_ID: research_status_config,
    ChatMode.ITERATIVE_RESEARCH_COMMAND_ID: research_status_config,
}


def write_slowly(message_placeholder, answer):
    """Write a message to the message placeholder slowly, like a typewriter."""
    for i in range(1, len(answer) + 1):
        message_placeholder.markdown(answer[:i])
        time.sleep(0.005)

def show_sources(sources: list[str] | None):
    """Show the sources if present."""
    if not sources:
        return
    with st.expander("Sources"):
        for source in sources:
            st.markdown(source)
