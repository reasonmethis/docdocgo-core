from enum import Enum
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler

JSONish = dict[str, Any]
PairwiseChatHistory = list[tuple[str, str]]
Callbacks = list[BaseCallbackHandler] | None

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


chat_modes_needing_llm = {
    ChatMode.WEB_COMMAND_ID,
    ChatMode.ITERATIVE_RESEARCH_COMMAND_ID,
    ChatMode.JUST_CHAT_COMMAND_ID,
    ChatMode.DETAILS_COMMAND_ID,
    ChatMode.QUOTES_COMMAND_ID,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
}


class ChatState:
    def __init__(
        self,
        operation_mode: OperationMode,
        chat_mode: ChatMode = ChatMode.NONE_COMMAND_ID,
        message: str = "",
        chat_history: PairwiseChatHistory | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        search_params: JSONish | None = None,
        vectorstore: Any = None,
        ws_data: Any = None,
        callbacks: Callbacks = None,
    ) -> None:
        self.operation_mode = operation_mode
        self.chat_mode = chat_mode
        self.message = message
        self.chat_history = chat_history or []
        self.chat_and_command_history = chat_and_command_history or []
        self.search_params = search_params or {}
        self.vectorstore = vectorstore
        self.ws_data = ws_data
        self.callbacks = callbacks

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)
