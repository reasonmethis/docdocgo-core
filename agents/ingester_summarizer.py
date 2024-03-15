import uuid

from langchain.schema import Document

from agents.dbmanager import (
    construct_full_collection_name,
    get_access_role,
    get_user_facing_collection_name,
)
from components.llm import get_prompt_llm_chain
from utils.chat_state import ChatState
from utils.docgrab import ingest_docs_into_chroma
from utils.helpers import (
    ADDITIVE_COLLECTION_PREFIX,
    INGESTED_DOCS_INIT_PREFIX,
    format_invalid_input_answer,
    format_nonstreaming_answer,
)
from utils.lang_utils import limit_tokens_in_text
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import SUMMARIZER_PROMPT
from utils.query_parsing import IngestCommand
from utils.type_utils import AccessRole, ChatMode
from utils.web import LinkData, get_batch_url_fetcher

DEFAULT_MAX_TOKENS_FINAL_CONTEXT = int(CONTEXT_LENGTH * 0.7)

NO_EDITOR_ACCESS_STATUS = "No editor access to collection"  # a bit of duplication


def get_ingester_summarizer_response(chat_state: ChatState):
    message = chat_state.parsed_query.message
    ingest_command = chat_state.parsed_query.ingest_command

    # Determine if we need to use the same collection or create a new one
    coll_name_as_shown = get_user_facing_collection_name(
        chat_state.user_id, chat_state.vectorstore.name
    )
    if ingest_command == IngestCommand.ADD or (
        ingest_command == IngestCommand.DEFAULT
        and coll_name_as_shown.startswith(ADDITIVE_COLLECTION_PREFIX)
    ):
        # We will use the same collection
        coll_name_full = chat_state.vectorstore.name

        # Check for editor access
        if get_access_role(chat_state).value < AccessRole.EDITOR.value:
            cmd_str = (
                "summarize"
                if chat_state.chat_mode == ChatMode.SUMMARIZE_COMMAND_ID
                else "ingest"
            )
            return format_invalid_input_answer(
                "Apologies, you can't ingest content into the current collection "
                "because you don't have editor access to it. You can ingest content "
                "into a new collection instead. For example:\n\n"
                f"```\n\n/{cmd_str} new {message}\n\n```",
                NO_EDITOR_ACCESS_STATUS,
            )
    else:
        # We will need to create a new collection
        coll_name_as_shown = INGESTED_DOCS_INIT_PREFIX + uuid.uuid4().hex[:8]
        coll_name_full = construct_full_collection_name(
            chat_state.user_id, coll_name_as_shown
        )

    # Fetch the content
    fetch_func = get_batch_url_fetcher()  # don't really need the batch aspect here
    html = fetch_func([message])[0]
    link_data = LinkData.from_raw_content(html)

    if link_data.error:
        return format_nonstreaming_answer(
            f"Apologies, I could not retrieve the resource `{message}`."
        )

    if chat_state.chat_mode == ChatMode.INGEST_COMMAND_ID:
        # "/ingest https://some.url.com" command - just ingest, don't summarize
        res = format_nonstreaming_answer(
            f"The resource `{message}` has been ingested into the collection "
            f"`{coll_name_as_shown}`. If you don't need to ingest "
            "more content into it, rename it by with `/db rename my-cool-collection-name`."
        )
    else:
        # "/summarize https://some.url.com" command
        summarizer_chain = get_prompt_llm_chain(
            SUMMARIZER_PROMPT,
            llm_settings=chat_state.bot_settings,
            api_key=chat_state.openai_api_key,
            callbacks=chat_state.callbacks,
        )

        text, num_tokens = limit_tokens_in_text(
            link_data.text, DEFAULT_MAX_TOKENS_FINAL_CONTEXT
        )  # TODO: ability to summarize longer content

        if text != link_data.text:
            text += "\n\nNOTE: The above content was truncated to fit the maximum token limit."

        res = {"answer": summarizer_chain.invoke({"content": text})}

    # Ingest into Chroma
    doc = Document(page_content=link_data.text, metadata={"source": message})
    ingest_docs_into_chroma(
        [doc],
        collection_name=coll_name_full,
        chroma_client=chat_state.vectorstore.client,
        openai_api_key=chat_state.openai_api_key,
        verbose=True,
    )

    if chat_state.vectorstore.name != coll_name_full:
        # Switch to the newly created collection
        vectorstore = chat_state.get_new_vectorstore(coll_name_full)
        res["vectorstore"] = vectorstore

    return res
