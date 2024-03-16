from pydantic import BaseModel, Field

from agents.researcher_data import ResearchReportData
from components.chroma_ddg import ChromaDDG, load_vectorstore
from utils.query_parsing import ParsedQuery
from utils.type_utils import (
    COLLECTION_USERS_METADATA_KEY,
    AccessCodeSettings,
    AccessRole,
    BotSettings,
    CallbacksOrNone,
    ChatMode,
    CollectionPermissions,
    CollectionUserSettings,
    OperationMode,
    PairwiseChatHistory,
    Props,
)


class ScheduledQueries(BaseModel):
    queue_: list[ParsedQuery] = Field(default_factory=list)

    def add_top(self, query: ParsedQuery) -> None:
        """Add a query to the top of the queue. This query will be executed next."""
        self.queue_.append(query)

    def add_bottom(self, query: ParsedQuery) -> None:
        """Add a query to the bottom of the queue. This query will be executed last."""
        self.queue_.insert(0, query)

    def pop(self) -> ParsedQuery | None:
        """Pop the next query from the queue. Returns None if the queue is empty."""
        try:
            return self.queue_.pop()
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
        vectorstore: ChromaDDG,
        is_community_key: bool = False,
        parsed_query: ParsedQuery | None = None,
        chat_history: PairwiseChatHistory | None = None,
        sources_history: list[list[str]] | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        callbacks: CallbacksOrNone = None,
        bot_settings: BotSettings | None = None,
        user_id: str | None = None,
        openai_api_key: str | None = None,
        scheduled_queries: ScheduledQueries | None = None,
        access_role_by_user_id_by_coll: dict[str, dict[str, AccessRole]] | None = None,
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
        self.access_role_by_user_id_by_coll = access_role_by_user_id_by_coll or {}

    @property
    def chat_mode(self) -> ChatMode:
        return self.parsed_query.chat_mode

    @property
    def message(self) -> str:
        return self.parsed_query.message

    @property
    def search_params(self) -> Props:
        return self.parsed_query.search_params or {}

    @property
    def vectorstore_client(self):
        return self.vectorstore.client

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def fetch_collection_metadata(self, coll_name: str | None = None) -> Props | None:
        """
        Fetch metadata for the currently selected collection, or for the given
        collection name if provided
        """
        if coll_name in (None, self.vectorstore.name):
            return self.vectorstore.fetch_collection_metadata()

        if tmp_vectorstore := self.get_new_vectorstore(
            coll_name, create_if_not_exists=False
        ):
            return tmp_vectorstore.fetch_collection_metadata()
        return None

    def get_rr_data(self) -> ResearchReportData | None:
        """
        Extract ResearchReportData from the currently selected collection's metadata
        """
        try:
            rr_data_json = self.fetch_collection_metadata()["rr_data"]
        except (TypeError, KeyError):
            return
        return ResearchReportData.model_validate_json(rr_data_json)

    def save_rr_data(self, rr_data: ResearchReportData) -> None:
        """
        Update the currently selected collection's metadata with the given ResearchReportData
        """
        coll_metadata = self.fetch_collection_metadata() or {}
        coll_metadata["rr_data"] = rr_data.model_dump_json()
        self.vectorstore.save_collection_metadata(coll_metadata)

    def get_collection_permissions(
        self, coll_name: str | None = None
    ) -> CollectionPermissions:
        """
        Get the collection user settings from the currently selected collection's
        metadata, or from the given collection name if provided
        """
        try:
            collection_permissions_json = self.fetch_collection_metadata(coll_name)[
                COLLECTION_USERS_METADATA_KEY
            ]
            print("\ncollection_permissions_json:\n", collection_permissions_json)
        except (TypeError, KeyError):
            return CollectionPermissions()
        return CollectionPermissions.model_validate_json(collection_permissions_json)

    def save_collection_permissions(
        self, collection_permissions: CollectionPermissions
    ) -> None:
        """
        Update the currently selected collection's metadata with the given CollectionUsers
        """
        coll_metadata = self.fetch_collection_metadata() or {}
        json_str = collection_permissions.model_dump_json()
        coll_metadata[COLLECTION_USERS_METADATA_KEY] = json_str
        self.vectorstore.save_collection_metadata(coll_metadata)

    def get_collection_settings_for_user(
        self, user_id: str | None, coll_name: str | None = None
    ) -> CollectionUserSettings:
        """
        Get the collection user settings for the given user from the currently selected collection's
        metadata, or from the specified collection
        """
        return self.get_collection_permissions(coll_name).get_user_settings(user_id)

    def save_collection_settings_for_user(
        self, user_id: str | None, settings: CollectionUserSettings
    ) -> None:
        """
        Update the currently selected collection's metadata with the given CollectionUserSettings
        """
        collection_permissions = self.get_collection_permissions()
        collection_permissions.set_user_settings(user_id, settings)
        self.save_collection_permissions(collection_permissions)

    def get_access_code_settings(
        self, access_code: str, coll_name: str | None = None
    ) -> AccessCodeSettings:
        """
        Get the access code settings from the currently selected collection's metadata,
        or from the specified collection
        """
        return self.get_collection_permissions(coll_name).get_access_code_settings(
            access_code
        )

    def save_access_code_settings(
        self, access_code: str, access_code_settings: AccessCodeSettings
    ) -> None:
        """
        Update the currently selected collection's metadata with the given AccessCodeSettings
        """
        collection_permissions = self.get_collection_permissions()
        collection_permissions.set_access_code_settings(
            access_code, access_code_settings
        )
        self.save_collection_permissions(collection_permissions)

    def get_new_vectorstore(
        self, collection_name: str, create_if_not_exists: bool = True
    ) -> ChromaDDG | None:
        """
        Get a new ChromaDDG instance with the given collection name. If the collection
        does not exist, either returns None or creates a new collection, depending on
        the value of create_if_not_exists (default: True).
        """
        return load_vectorstore(
            collection_name,
            openai_api_key=self.openai_api_key,
            client=self.vectorstore.client,
            create_if_not_exists=create_if_not_exists,
        )
