import re
import time

import streamlit as st

from utils.type_utils import ChatMode

allowed_extensions = ["", ".txt", ".md", ".rtf", ".log", ".pdf", ".docx", ".html", ".htm"]

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
    ChatMode.RESEARCH_COMMAND_ID: research_status_config,
}


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


def write_slowly(message_placeholder, answer):
    """Write a message to the message placeholder slowly, character by character."""
    delay = min(0.005, 2 / (len(answer) + 1))
    for i in range(1, len(answer) + 1):
        message_placeholder.markdown(fix_markdown(answer[:i]))
        time.sleep(delay)


def show_sources(sources: list[str] | None):
    """Show the sources if present."""
    if not sources:
        return
    with st.expander("Sources"):
        for source in sources:
            st.markdown(source)
