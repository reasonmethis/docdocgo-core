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
    "complete.body": "Report composed and sources added to the database.",
}

status_config = {
    ChatMode.JUST_CHAT_COMMAND_ID: just_chat_status_config,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID: default_status_config,
    ChatMode.DETAILS_COMMAND_ID: default_status_config,
    ChatMode.QUOTES_COMMAND_ID: default_status_config,
    ChatMode.WEB_COMMAND_ID: research_status_config,
    ChatMode.ITERATIVE_RESEARCH_COMMAND_ID: research_status_config,
}

