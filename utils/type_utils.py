from enum import Enum
from typing import Any

from langchain.callbacks.base import BaseCallbackHandler
from pydantic import BaseModel, Field

from utils.prepare import MODEL_NAME, TEMPERATURE

JSONish = dict[str, Any] | list
Props = dict[str, Any]
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
    RESEARCH_COMMAND_ID = 5
    JUST_CHAT_COMMAND_ID = 6
    DB_COMMAND_ID = 7
    HELP_COMMAND_ID = 8
    INGEST_COMMAND_ID = 9
    BROWSE_COMMAND_ID = 10
    SUMMARIZE_COMMAND_ID = 11


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


AccessRole = Enum("AccessRole", "EDITOR VIEWER NONE")
SharerRole = Enum("SharerRole", "EDITOR VIEWER NONE")


class CollectionUserSettings(BaseModel):
    access_role: AccessRole = AccessRole.NONE
    sharer_role: SharerRole = SharerRole.NONE

COLLECTION_USERS_METADATA_KEY = "collection_users"

class CollectionUsers(BaseModel):
    userid_to_settings: dict[str, CollectionUserSettings] = Field(default_factory=dict)
    # NOTE: key "" refers to settings for a general user

    def get_settings(self, userid: str | None) -> CollectionUserSettings:
        return self.userid_to_settings.get(userid or "", CollectionUserSettings())
