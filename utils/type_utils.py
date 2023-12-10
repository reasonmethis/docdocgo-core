from typing import Any

from langchain.callbacks.base import BaseCallbackHandler

JSONish = dict[str, Any]
PairwiseChatHistory = list[tuple[str, str]]
Callbacks = list[BaseCallbackHandler] | None

class ChatState:
    def __init__(
        self,
        command_id: int,
        message: str = "",
        chat_history: PairwiseChatHistory | None = None,
        search_params: JSONish | None = None,
        vectorstore: Any = None,
        ws_data: Any = None,
        callbacks: Callbacks = None,
    ) -> None:
        self.command_id = command_id
        self.message = message
        self.chat_history = chat_history or []
        self.search_params = search_params or {}
        self.vectorstore = vectorstore
        self.ws_data = ws_data
        self.callbacks = callbacks
