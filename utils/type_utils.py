from enum import Enum
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler
from pydantic import BaseModel, Field

from utils.prepare import MODEL_NAME, TEMPERATURE

JSONish = dict[str, Any] | list
Props = dict[str, Any]
PairwiseChatHistory = list[tuple[str, str]]
CallbacksOrNone = list[BaseCallbackHandler] | None

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
    BROWSE_COMMAND_ID = 10
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


class BotSettings(BaseModel):
    llm_model_name: str = MODEL_NAME
    temperature: float = TEMPERATURE


AccessRole = Enum("AccessRole", {"NONE": 0, "VIEWER": 1, "EDITOR": 2, "OWNER": 3})
# SharerRole = Enum("SharerRole", "EDITOR VIEWER NONE")

AccessCodeType = Enum("AccessCodeType", "NEED_ALWAYS NEED_ONCE NO_ACCESS")


class CollectionUserSettings(BaseModel):
    access_role: AccessRole = AccessRole.NONE
    # sharer_role: SharerRole = SharerRole.NONE


class AccessCodeSettings(BaseModel):
    code_type: AccessCodeType = AccessCodeType.NO_ACCESS
    access_role: AccessRole = AccessRole.NONE
    # sharer_role: SharerRole = SharerRole.NONE


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
