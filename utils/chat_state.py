import json
from typing import Callable

from chromadb import Collection
from pydantic import BaseModel, Field

from agents.researcher_data import ResearchReportData
from components.chroma_ddg import (
    ChromaDDG,
    CollectionDoesNotExist,
    get_vectorstore_using_openai_api_key,
)
from components.llm import get_prompt_llm_chain
from utils.helpers import (
    PRIVATE_COLLECTION_PREFIX,
    PRIVATE_COLLECTION_USER_ID_LENGTH,
    get_timestamp,
)
from utils.prepare import DEFAULT_COLLECTION_NAME, get_logger
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
    JSONishDict,
    OperationMode,
    PairwiseChatHistory,
    Props,
)
from langchain_core.documents import Document

logger = get_logger()


class ScheduledQueries(BaseModel):
    queue_: list[ParsedQuery] = Field(default_factory=list)

    def add_to_front(self, query: ParsedQuery) -> None:
        """Add a query to the top of the queue. This query will be executed next."""
        self.queue_.append(query)

    def add_to_back(self, query: ParsedQuery) -> None:
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


AgentDataDict = dict[str, JSONishDict]  # e.g. {"hs_data": {"links": [...], "blah": 3}}


class ChatState:
    def __init__(
        self,
        *,
        operation_mode: OperationMode,
        vectorstore: ChromaDDG,
        is_community_key: bool = False,
        parsed_query: ParsedQuery | None = None,
        chat_history: PairwiseChatHistory | None = None,
        chat_and_command_history: PairwiseChatHistory | None = None,
        sources_history: list[list[str]] | None = None,
        callbacks: CallbacksOrNone = None,
        add_to_output: Callable | None = None,
        bot_settings: BotSettings | None = None,
        user_id: str | None = None,  # NOTE: should switch to "" instead of None
        openai_api_key: str | None = None,
        scheduled_queries: ScheduledQueries | None = None,
        access_role_by_user_id_by_coll: dict[str, dict[str, AccessRole]] | None = None,
        access_code_by_coll_by_user_id: dict[str, dict[str, str]] | None = None,
        uploaded_docs: list[Document] | None = None,
        session_data: AgentDataDict | None = None,  # currently not used (agent
        # data is stored in collection metadata)
    ) -> None:
        self.operation_mode = operation_mode
        self.is_community_key = is_community_key
        self.parsed_query = parsed_query or ParsedQuery()
        self.chat_history = chat_history or []  # tuple of (user_message, bot_response)
        self.chat_history_all = chat_and_command_history or []
        self.sources_history = sources_history or []  # used only in Streamlit for now
        self.vectorstore = vectorstore
        self.callbacks = callbacks
        self.add_to_output = add_to_output or (
            lambda *args: print(args[0], end="", flush=True)
        )
        self.bot_settings = bot_settings or BotSettings()
        self.user_id = user_id
        self.openai_api_key = openai_api_key
        self.scheduled_queries = scheduled_queries or ScheduledQueries()
        self._access_role_by_user_id_by_coll = access_role_by_user_id_by_coll or {}
        self._access_code_by_coll_by_user_id = access_code_by_coll_by_user_id or {}
        self.uploaded_docs = uploaded_docs or []
        self.session_data = session_data or {}

    @property
    def collection_name(self) -> str:
        return self.vectorstore.name

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
    def db_client(self):
        return self.vectorstore.client

    def update(self, **kwargs) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)

    def get_all_collections(self) -> list[Collection]:
        """Get all collections."""
        return self.db_client.list_collections()

    def get_user_collections(self) -> list[Collection]:
        """
        Get the accessible collections for the current user.
        """
        collections = self.db_client.list_collections()  # TODO: here and elsewhere,
        # introduce limit and offset for pagination when there are many collections
        cached_accessible_coll_names = {
            coll_name
            for coll_name in self._access_role_by_user_id_by_coll.keys()
            if self.get_cached_access_role(coll_name).value > AccessRole.NONE.value
        }  # some may have been deleted or renamed but that's taken care of below

        if self.user_id:
            short_user_id = self.user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:]
            prefix = PRIVATE_COLLECTION_PREFIX + short_user_id

            cached_accessible_coll_names.add(DEFAULT_COLLECTION_NAME)  # for efficiency
            filtered_collections = [
                c
                for c in collections
                if c.name.startswith(prefix) or c.name in cached_accessible_coll_names
            ]
        else:
            filtered_collections = [
                c
                for c in collections
                if not c.name.startswith(PRIVATE_COLLECTION_PREFIX)
                or c.name in cached_accessible_coll_names
            ]

        return filtered_collections

    def fetch_collection_metadata(self, coll_name: str | None = None) -> Props | None:
        """
        Fetch metadata for the currently selected collection, or for the given
        collection name if provided. If the collection does not exist, returns None.
        """
        if coll_name in (None, self.vectorstore.name):
            return self.vectorstore.fetch_collection_metadata()
        elif tmp_vectorstore := self.get_new_vectorstore(
            coll_name, create_if_not_exists=False
        ):
            # return tmp_vectorstore.fetch_collection_metadata()
            # Since we fetched a new vectorstore, it includes the latest metadata
            return tmp_vectorstore.get_cached_collection_metadata()
        else:
            return None  # redundant but for clarity

    def get_cached_collection_metadata(self) -> Props | None:
        return self.vectorstore.get_cached_collection_metadata()

    def get_collection_metadata(
        self, use_cached_metadata: bool = False
    ) -> Props | None:
        """
        Get the metadata for the currently selected collection, either from the cache
        or by fetching it from the database, depending on the value of use_cached_metadata.
        """
        return (
            self.vectorstore.get_cached_collection_metadata()
            if use_cached_metadata
            else self.vectorstore.fetch_collection_metadata()
        )

    def save_collection_metadata(self, metadata: Props) -> None:
        """
        Update the metadata for the currently selected collection
        """
        metadata["updated_at"] = get_timestamp()
        self.vectorstore.save_collection_metadata(metadata)

    def get_agent_data(self, use_cached_metadata: bool = False) -> AgentDataDict:
        """
        Extract agent data from the currently selected collection's metadata
        """
        try:
            agent_data = self.get_collection_metadata(use_cached_metadata)["agent_data"]
            return json.loads(agent_data)
        except (TypeError, KeyError):
            return {}

    def save_agent_data(
        self, agent_data: AgentDataDict, use_cached_metadata: bool = False
    ) -> None:
        """
        Update the currently selected collection's metadata with the given agent data
        """
        # NOTE: currently, agent_data is assumed to be able to have only one key at
        # a time for a given collection, such as "hs" or "rr".
        coll_metadata = self.get_collection_metadata(use_cached_metadata) or {}
        coll_metadata["agent_data"] = json.dumps(agent_data)
        self.save_collection_metadata(coll_metadata)

    def get_rr_data(
        self, use_cached_metadata: bool = False
    ) -> ResearchReportData | None:
        """
        Extract ResearchReportData from the currently selected collection's metadata
        """
        logger.info("Getting rr_data")
        coll_metadata = self.get_collection_metadata(use_cached_metadata)
        try:
            rr_data_json = coll_metadata["rr_data"]
        except (TypeError, KeyError):
            logger.info("No rr_data found")
            return None
        logger.info("rr_data retrieved.")
        return ResearchReportData.model_validate_json(rr_data_json)

    def save_rr_data(
        self, rr_data: ResearchReportData, use_cached_metadata: bool = False
    ) -> None:
        """
        Update the currently selected collection's metadata with the given ResearchReportData
        """
        coll_metadata = self.get_collection_metadata(use_cached_metadata) or {}
        coll_metadata["rr_data"] = rr_data.model_dump_json()
        self.save_collection_metadata(coll_metadata)

    def get_collection_permissions(
        self, coll_name: str | None = None, use_cached_metadata: bool = False
    ) -> CollectionPermissions:
        """
        Get the collection user settings from the currently selected collection's
        metadata, or from the given collection name if provided
        """
        try:
            if use_cached_metadata and coll_name is None:
                coll_metadata = self.get_cached_collection_metadata()
            else:
                coll_metadata = self.fetch_collection_metadata(coll_name)
            collection_permissions_json = coll_metadata[COLLECTION_USERS_METADATA_KEY]
            logger.info(f"Permissions for {coll_name}:\n{collection_permissions_json}")
        except (TypeError, KeyError):
            return CollectionPermissions()
        return CollectionPermissions.model_validate_json(collection_permissions_json)

    def save_collection_permissions(
        self,
        collection_permissions: CollectionPermissions,
        use_cached_metadata: bool = False,
    ) -> None:
        """
        Update the currently selected collection's metadata with the given CollectionUsers
        """
        coll_metadata = self.get_collection_metadata(use_cached_metadata) or {}
        json_str = collection_permissions.model_dump_json()
        coll_metadata[COLLECTION_USERS_METADATA_KEY] = json_str
        self.save_collection_metadata(coll_metadata)

    def get_collection_settings_for_user(
        self,
        user_id: str | None,
        coll_name: str | None = None,
        use_cached_metadata: bool = False,
    ) -> CollectionUserSettings:
        """
        Get the collection user settings for the given user from the currently selected collection's
        metadata, or from the specified collection
        """
        return self.get_collection_permissions(
            coll_name, use_cached_metadata=use_cached_metadata
        ).get_user_settings(user_id)

    def save_collection_settings_for_user(
        self,
        user_id: str | None,
        settings: CollectionUserSettings,
        use_cached_metadata: bool = False,
    ) -> None:
        """
        Update the currently selected collection's metadata with the given CollectionUserSettings
        """
        collection_permissions = self.get_collection_permissions(
            use_cached_metadata=use_cached_metadata
        )
        collection_permissions.set_user_settings(user_id, settings)
        self.save_collection_permissions(
            collection_permissions,
            use_cached_metadata=True,  # since we just fetched it
        )

    def get_access_code_settings(
        self,
        access_code: str,
        coll_name: str | None = None,
        use_cached_metadata: bool = False,
    ) -> AccessCodeSettings:
        """
        Get the access code settings from the currently selected collection's metadata,
        or from the specified collection
        """
        return self.get_collection_permissions(
            coll_name, use_cached_metadata=use_cached_metadata
        ).get_access_code_settings(access_code)

    def save_access_code_settings(
        self,
        access_code: str,
        access_code_settings: AccessCodeSettings,
        use_cached_metadata: bool = False,
    ) -> None:
        """
        Update the currently selected collection's metadata with the given AccessCodeSettings
        """
        collection_permissions = self.get_collection_permissions(
            use_cached_metadata=use_cached_metadata
        )
        collection_permissions.set_access_code_settings(
            access_code, access_code_settings
        )
        self.save_collection_permissions(
            collection_permissions,
            use_cached_metadata=True,  # since we just fetched it
        )

    def get_cached_access_role(self, coll_name: str | None = None) -> AccessRole:
        """
        Get the access role for the current or provided collection that was cached
        in the chat state during the current session.
        """
        return self._access_role_by_user_id_by_coll.get(
            coll_name or self.collection_name, {}
        ).get(self.user_id or "", AccessRole.NONE)

    def set_cached_access_role(
        self, access_role: AccessRole, coll_name: str | None = None
    ):
        """
        Cache the user's access role for the current or provided collection.
        """
        self._access_role_by_user_id_by_coll.setdefault(
            coll_name or self.collection_name, {}
        )[self.user_id or ""] = access_role

    def get_cached_access_code(self, coll_name: str | None = None) -> str | None:
        """
        Get the cached access code for the current or provided collection.
        """
        return self._access_code_by_coll_by_user_id.get(self.user_id, {}).get(
            coll_name or self.collection_name
        )

    def set_cached_access_code(self, access_code: str, coll_name: str | None = None):
        """
        Cache the access code for the current or provided collection.
        """
        self._access_code_by_coll_by_user_id.setdefault(self.user_id, {})[
            coll_name or self.collection_name
        ] = access_code

    def get_new_vectorstore(
        self, collection_name: str, create_if_not_exists: bool = True
    ) -> ChromaDDG | None:
        """
        Get a new ChromaDDG instance with the given collection name. If the collection
        does not exist, either returns None or creates a new collection, depending on
        the value of create_if_not_exists (default: True).
        """
        try:
            return get_vectorstore_using_openai_api_key(
                collection_name,
                openai_api_key=self.openai_api_key,
                client=self.vectorstore.client,
                create_if_not_exists=create_if_not_exists,
            )
        except CollectionDoesNotExist:
            return None

    def get_prompt_llm_chain(self, prompt, *, to_user: bool):
        return get_prompt_llm_chain(
            prompt,
            llm_settings=self.bot_settings,
            api_key=self.openai_api_key,
            stream=to_user,
            callbacks=self.callbacks if to_user else None,
        )

    def get_llm_reply(self, prompt, inputs, *, to_user: bool):
        return self.get_prompt_llm_chain(prompt, to_user=to_user).invoke(inputs)
