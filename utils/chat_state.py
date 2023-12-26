from agents.websearcher_data import WebsearcherData
from components.chroma_ddg import ChromaDDG
from utils.type_utils import (
    BotSettings,
    CallbacksOrNone,
    ChatMode,
    JSONish,
    OperationMode,
    PairwiseChatHistory,
)


class ChatState:
    def __init__(
        self,
        operation_mode: OperationMode,
        chat_mode: ChatMode = ChatMode.NONE_COMMAND_ID,
        message: str = "",
        chat_history: PairwiseChatHistory | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        search_params: JSONish | None = None,
        vectorstore: ChromaDDG | None = None,
        callbacks: CallbacksOrNone = None,
        bot_settings: BotSettings | None = None,
    ) -> None:
        self.operation_mode = operation_mode
        self.chat_mode = chat_mode
        self.message = message
        self.chat_history = chat_history or []
        self.chat_and_command_history = chat_and_command_history or []
        self.search_params = search_params or {}
        self.vectorstore = vectorstore
        self.callbacks = callbacks
        self.bot_settings = bot_settings or BotSettings()

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def save_ws_data(self, ws_data: WebsearcherData) -> None:
        """
        Update the currently selected collection's metadata with the given WebsearcherData
        """
        if self.vectorstore is None:
            raise ValueError("No vectorstore selected")
        coll_metadata = self.vectorstore.get_collection_metadata() or {}
        coll_metadata["ws_data"] = ws_data.json()
        self.vectorstore.set_collection_metadata(coll_metadata)

    @property
    def ws_data(self) -> WebsearcherData | None:
        """
        Extract WebsearcherData from the currently selected collection's metadata
        """
        if self.vectorstore is None:
            return None
        if not (coll_metadata := self.vectorstore.get_collection_metadata()):
            return None
        try:
            ws_data_json = coll_metadata["ws_data"]
        except KeyError:
            return None
        return WebsearcherData.parse_raw(ws_data_json)
