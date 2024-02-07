from pydantic import BaseModel, Field

from agents.researcher_data import ResearchReportData
from components.chroma_ddg import ChromaDDG, load_vectorstore
from utils.query_parsing import ParsedQuery
from utils.type_utils import (
    BotSettings,
    CallbacksOrNone,
    ChatMode,
    OperationMode,
    PairwiseChatHistory,
    Props,
)


class ScheduledQueries(BaseModel):
    queue_: list[ParsedQuery] = Field(default_factory=list)

    def add(self, query: ParsedQuery) -> None:
        self.queue_.append(query)

    def pop(self) -> ParsedQuery | None:
        try:
            return self.queue_.pop(0)
        except IndexError:
            return None

    def __len__(self) -> int:
        return len(self.queue_)

    def __bool__(self) -> bool:
        return bool(self.queue_)


class ChatState:
    def __init__(
        self,
        *,
        operation_mode: OperationMode,
        is_community_key: bool = False,
        parsed_query: ParsedQuery | None = None,
        chat_history: PairwiseChatHistory | None = None,
        sources_history: list[list[str]] | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        vectorstore: ChromaDDG | None = None,
        callbacks: CallbacksOrNone = None,
        bot_settings: BotSettings | None = None,
        user_id: str | None = None,
        openai_api_key: str | None = None,
        scheduled_queries: ScheduledQueries | None = None,
    ) -> None:
        self.operation_mode = operation_mode
        self.is_community_key = is_community_key
        self.parsed_query = parsed_query or ParsedQuery()
        self.chat_history = chat_history or []
        self.sources_history = sources_history or []  # used only in Streamlit for now
        self.chat_and_command_history = chat_and_command_history or []
        self.vectorstore = vectorstore
        self.callbacks = callbacks
        self.bot_settings = bot_settings or BotSettings()
        self.user_id = user_id
        self.openai_api_key = openai_api_key
        self.scheduled_queries = scheduled_queries or ScheduledQueries()

    @property
    def chat_mode(self) -> ChatMode:
        return self.parsed_query.chat_mode

    @property
    def message(self) -> str:
        return self.parsed_query.message

    @property
    def search_params(self) -> Props:
        return self.parsed_query.search_params or {}

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def save_rr_data(self, rr_data: ResearchReportData) -> None:
        """
        Update the currently selected collection's metadata with the given ResearchReportData
        """
        if self.vectorstore is None:
            raise ValueError("No vectorstore selected")
        coll_metadata = self.vectorstore.get_collection_metadata() or {}
        coll_metadata["rr_data"] = rr_data.model_dump_json()
        self.vectorstore.set_collection_metadata(coll_metadata)

    @property # TODO: turn into a method
    def get_rr_data(self) -> ResearchReportData | None:
        """
        Extract ResearchReportData from the currently selected collection's metadata
        """
        if self.vectorstore is None:
            return None
        if not (coll_metadata := self.vectorstore.get_collection_metadata()):
            return None
        try:
            rr_data_json = coll_metadata["rr_data"]
        except KeyError:
            return None
        return ResearchReportData.model_validate_json(rr_data_json)

    def get_new_vectorstore(self, collection_name: str) -> ChromaDDG:
        """
        Get a new ChromaDDG instance with the given collection name
        """
        return load_vectorstore(
            collection_name,
            openai_api_key=self.openai_api_key,
            client=self.vectorstore.client,
        )
