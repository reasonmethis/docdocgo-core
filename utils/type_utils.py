from enum import Enum
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler
from pydantic import BaseModel

from utils.prepare import MODEL_NAME, TEMPERATURE

JSONish = dict[str, Any] | list
PairwiseChatHistory = list[tuple[str, str]]
CallbacksOrNone = list[BaseCallbackHandler] | None

OperationMode = Enum("OperationMode", "CONSOLE STREAMLIT FLASK")


class ChatMode(Enum):
    NONE_COMMAND_ID = -1
    RETRY_COMMAND_ID = 0
    CHAT_WITH_DOCS_COMMAND_ID = 1
    DETAILS_COMMAND_ID = 2
    QUOTES_COMMAND_ID = 3
    WEB_COMMAND_ID = 4
    ITERATIVE_RESEARCH_COMMAND_ID = 5
    JUST_CHAT_COMMAND_ID = 6
    DB_COMMAND_ID = 7
    HELP_COMMAND_ID = 8
    INGEST_COMMAND_ID = 9


chat_modes_needing_llm = {
    ChatMode.WEB_COMMAND_ID,
    ChatMode.ITERATIVE_RESEARCH_COMMAND_ID,
    ChatMode.JUST_CHAT_COMMAND_ID,
    ChatMode.DETAILS_COMMAND_ID,
    ChatMode.QUOTES_COMMAND_ID,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
}


class BotSettings(BaseModel):
    llm_model_name: str = MODEL_NAME
    temperature: float = TEMPERATURE
