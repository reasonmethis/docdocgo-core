from enum import Enum
from typing import Any
from langchain_core.documents.base import Document
from langchain_core.runnables import RunnableSerializable
from pydantic import BaseModel, Field

from utils.prepare import MODEL_NAME, TEMPERATURE
from langchain_core.callbacks import BaseCallbackHandler

JSONish = str | int | float | dict[str, "JSONish"] | list["JSONish"]
JSONishDict = dict[str, JSONish]
JSONishSimple = str | int | float | dict[str, Any] | list  # for use in pydantic models
Props = dict[str, Any]

PairwiseChatHistory = list[tuple[str, str]]
CallbacksOrNone = list[BaseCallbackHandler] | None
ChainType = RunnableSerializable[dict, str]  # double check this

OperationMode = Enum("OperationMode", "CONSOLE STREAMLIT FASTAPI")


class ChatMode(Enum):
    NONE_COMMAND_ID = -1
    RETRY_COMMAND_ID = 0
    CHAT_WITH_DOCS_COMMAND_ID = 1
    DETAILS_COMMAND_ID = 2
    QUOTES_COMMAND_ID = 3
    WEB_COMMAND_ID = 4
    RESEARCH_COMMAND_ID = 5
    JUST_CHAT_COMMAND_ID = 6
    DB_COMMAND_ID = 7
    HELP_COMMAND_ID = 8
    INGEST_COMMAND_ID = 9
    EXPORT_COMMAND_ID = 10
    SUMMARIZE_COMMAND_ID = 11
    SHARE_COMMAND_ID = 12


chat_modes_needing_llm = {
    ChatMode.WEB_COMMAND_ID,
    ChatMode.RESEARCH_COMMAND_ID,
    ChatMode.JUST_CHAT_COMMAND_ID,
    ChatMode.DETAILS_COMMAND_ID,
    ChatMode.QUOTES_COMMAND_ID,
    ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
    ChatMode.SUMMARIZE_COMMAND_ID,
    ChatMode.HELP_COMMAND_ID,
}


class DDGError(Exception):
    default_user_facing_message = (
        "Apologies, I ran into some trouble when preparing a response to you."
    )
    default_http_status_code = 500

    def __init__(
        self,
        message: str | None = None,
        user_facing_message: str | None = None,
        http_status_code: int | None = None,
    ):
        super().__init__(message)  # could include user_facing_message

        if user_facing_message is not None:
            self.user_facing_message = user_facing_message
        else:
            self.user_facing_message = self.default_user_facing_message

        if http_status_code is not None:
            self.http_status_code = http_status_code
        else:
            self.http_status_code = self.default_http_status_code

    @property
    def user_facing_message_full(self):
        if self.__cause__ is None:
            return self.user_facing_message
        return (
            f"{self.user_facing_message} The error reads:\n```\n{self.__cause__}\n```"
        )


class BotSettings(BaseModel):
    llm_model_name: str = MODEL_NAME
    temperature: float = TEMPERATURE


AccessRole = Enum("AccessRole", {"NONE": 0, "VIEWER": 1, "EDITOR": 2, "OWNER": 3})

AccessCodeType = Enum("AccessCodeType", "NEED_ALWAYS NEED_ONCE NO_ACCESS")


class CollectionUserSettings(BaseModel):
    access_role: AccessRole = AccessRole.NONE


class AccessCodeSettings(BaseModel):
    code_type: AccessCodeType = AccessCodeType.NO_ACCESS
    access_role: AccessRole = AccessRole.NONE


COLLECTION_USERS_METADATA_KEY = "collection_users"


class CollectionPermissions(BaseModel):
    user_id_to_settings: dict[str, CollectionUserSettings] = Field(default_factory=dict)
    # NOTE: key "" refers to settings for a general user

    access_code_to_settings: dict[str, AccessCodeSettings] = Field(default_factory=dict)

    def get_user_settings(self, user_id: str | None) -> CollectionUserSettings:
        return self.user_id_to_settings.get(user_id or "", CollectionUserSettings())

    def set_user_settings(
        self, user_id: str | None, settings: CollectionUserSettings
    ) -> None:
        self.user_id_to_settings[user_id or ""] = settings

    def get_access_code_settings(self, access_code: str) -> AccessCodeSettings:
        return self.access_code_to_settings.get(access_code, AccessCodeSettings())

    def set_access_code_settings(
        self, access_code: str, settings: AccessCodeSettings
    ) -> None:
        self.access_code_to_settings[access_code] = settings


INSTRUCT_SHOW_UPLOADER = "INSTRUCT_SHOW_UPLOADER"
INSTRUCT_CACHE_ACCESS_CODE = "INSTRUCT_CACHE_ACCESS_CODE"
INSTRUCT_AUTO_RUN_NEXT_QUERY = "INSTRUCT_AUTO_RUN_NEXT_QUERY"
INSTRUCT_EXPORT_CHAT_HISTORY = "INSTRUCT_EXPORT_CHAT_HISTORY"
# INSTRUCTION_SKIP_CHAT_HISTORY = "INSTRUCTION_SKIP_CHAT_HISTORY"


class Instruction(BaseModel):
    type: str
    user_id: str | None = None
    access_code: str | None = None
    data: JSONishSimple | None = None  # NOTE: absorb the two fields above into this one


class Doc(BaseModel):
    """Pydantic-compatible version of Langchain's Document."""

    page_content: str
    metadata: dict[str, Any]

    @staticmethod
    def from_lc_doc(langchain_doc: Document) -> "Doc":
        return Doc(
            page_content=langchain_doc.page_content, metadata=langchain_doc.metadata
        )

    def to_lc_doc(self) -> Document:
        return Document(page_content=self.page_content, metadata=self.metadata)
