from enum import Enum
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler

JSONish = dict[str, Any]
PairwiseChatHistory = list[tuple[str, str]]
Callbacks = list[BaseCallbackHandler] | None

OperationMode = Enum("OperationMode", "CONSOLE STREAMLIT FLASK")


class ChatState:
    def __init__(
        self,
        operation_mode: OperationMode,
        command_id: int = -1,
        message: str = "",
        chat_history: PairwiseChatHistory | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        search_params: JSONish | None = None,
        vectorstore: Any = None,
        ws_data: Any = None,
        callbacks: Callbacks = None,
    ) -> None:
        self.operation_mode = operation_mode
        self.command_id = command_id
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
