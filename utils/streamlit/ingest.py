import uuid

import streamlit as st

from agentblocks.collectionhelper import ingest_into_collection
from agents.dbmanager import (
    get_full_collection_name,
    get_user_facing_collection_name,
)
from utils.chat_state import ChatState
from utils.helpers import ADDITIVE_COLLECTION_PREFIX, INGESTED_DOCS_INIT_PREFIX
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.query_parsing import IngestCommand
from utils.streamlit.helpers import (
    POST_INGEST_MESSAGE_TEMPLATE_EXISTING_COLL,
    POST_INGEST_MESSAGE_TEMPLATE_NEW_COLL,
)
from langchain_core.documents import Document


def ingest_docs(docs: list[Document], chat_state: ChatState):
    ingest_command = chat_state.parsed_query.ingest_command

    uploaded_docs_coll_name_as_shown = get_user_facing_collection_name(
        chat_state.user_id, chat_state.vectorstore.name
    )  # might reassign below
    if chat_state.vectorstore.name != DEFAULT_COLLECTION_NAME and (
        ingest_command == IngestCommand.ADD
        or (
            ingest_command == IngestCommand.DEFAULT
            and uploaded_docs_coll_name_as_shown.startswith(ADDITIVE_COLLECTION_PREFIX)
        )
    ):
        # We will use the same collection
        is_new_collection = False
        uploaded_docs_coll_name_full = chat_state.vectorstore.name

        # Fetch the collection metadata so we can add timestamps
        collection_metadata = chat_state.fetch_collection_metadata()
    else:
        # We will need to create a new collection
        is_new_collection = True
        collection_metadata = {}
        uploaded_docs_coll_name_as_shown = (
            INGESTED_DOCS_INIT_PREFIX + uuid.uuid4().hex[:8]
        )
        uploaded_docs_coll_name_full = get_full_collection_name(
            chat_state.user_id, uploaded_docs_coll_name_as_shown
        )
    try:
        vectorstore = ingest_into_collection(
            collection_name=uploaded_docs_coll_name_full,
            docs=docs,
            collection_metadata=collection_metadata,
            chat_state=chat_state,
            is_new_collection=is_new_collection,
        )
        if is_new_collection:
            # Switch to the newly created collection
            chat_state.vectorstore = vectorstore
            msg_template = POST_INGEST_MESSAGE_TEMPLATE_NEW_COLL
        else:
            msg_template = POST_INGEST_MESSAGE_TEMPLATE_EXISTING_COLL

        with st.chat_message("assistant", avatar=st.session_state.bot_avatar):
            st.markdown(msg_template.format(coll_name=uploaded_docs_coll_name_as_shown))
    except Exception as e:
        with st.chat_message("assistant", avatar=st.session_state.bot_avatar):
            st.markdown(
                f"Apologies, an error occurred during ingestion:\n```\n{e}\n```"
            )
