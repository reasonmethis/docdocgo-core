import uuid

from icecream import ic

from agentblocks.collectionhelper import ingest_into_collection
from agents.dbmanager import (
    get_access_role,
    get_full_collection_name,
    get_user_facing_collection_name,
)
from components.llm import get_prompt_llm_chain
from utils.chat_state import ChatState
from utils.helpers import (
    ADDITIVE_COLLECTION_PREFIX,
    INGESTED_DOCS_INIT_PREFIX,
    format_invalid_input_answer,
    format_nonstreaming_answer,
)
from utils.lang_utils import limit_tokens_in_text, limit_tokens_in_texts
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import SUMMARIZER_PROMPT
from utils.query_parsing import IngestCommand
from utils.type_utils import INSTRUCT_SHOW_UPLOADER, AccessRole, ChatMode, Instruction
from utils.web import LinkData, get_batch_url_fetcher
from langchain_core.documents import Document

DEFAULT_MAX_TOKENS_FINAL_CONTEXT = int(CONTEXT_LENGTH * 0.7)

NO_EDITOR_ACCESS_STATUS = "No editor access to collection"  # a bit of duplication
NO_MULTIPLE_INGESTION_SOURCES_STATUS = (
    "Cannot ingest uploaded files and an external resource at the same time"
)
DOC_SEPARATOR = "\n" + "-" * 40 + "\n\n"


def summarize(docs: list[Document], chat_state: ChatState) -> str:
    if (num_docs := len(docs)) == 0:
        return ""

    summarizer_chain = get_prompt_llm_chain(
        SUMMARIZER_PROMPT,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
        callbacks=chat_state.callbacks,
    )

    if num_docs == 1:
        shortened_text, num_tokens = limit_tokens_in_text(
            docs[0].page_content, DEFAULT_MAX_TOKENS_FINAL_CONTEXT
        )  # TODO: ability to summarize longer content
        shortened_texts = [shortened_text]
    else:
        # Multiple documents
        shortened_texts, nums_of_tokens = limit_tokens_in_texts(
            [doc.page_content for doc in docs], DEFAULT_MAX_TOKENS_FINAL_CONTEXT
        )

    # Construct the final context
    final_texts = []
    for i, (doc, shortened_text) in enumerate(zip(docs, shortened_texts)):
        if doc.page_content != shortened_text:
            suffix = "\n\nNOTE: The above content was truncated to fit the maximum token limit."
        else:
            suffix = ""

        final_texts.append(
            f"SOURCE: {doc.metadata.get('source', 'Unknown')}"
            f"\n\n{shortened_text}{suffix}"
        )

    final_context = DOC_SEPARATOR.join(final_texts)
    ic(final_context)

    return summarizer_chain.invoke({"content": final_context})


def get_ingester_summarizer_response(chat_state: ChatState):
    # TODO: remove similar functionality in streamlit/ingest.py
    message = chat_state.parsed_query.message
    ingest_command = chat_state.parsed_query.ingest_command

    # If there's no message and no docs, just return request for files
    if not (docs := chat_state.uploaded_docs) and not message:
        return {
            "answer": "Please select your documents to upload and ingest.",
            "instructions": [Instruction(type=INSTRUCT_SHOW_UPLOADER)],
        }

    # Determine if we need to use the same collection or create a new one
    coll_name_as_shown = get_user_facing_collection_name(
        chat_state.user_id, chat_state.vectorstore.name
    )
    if ingest_command == IngestCommand.ADD or (
        ingest_command == IngestCommand.DEFAULT
        and coll_name_as_shown.startswith(ADDITIVE_COLLECTION_PREFIX)
    ):
        # We will use the same collection
        is_new_collection = False
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
        is_new_collection = True
        coll_name_as_shown = INGESTED_DOCS_INIT_PREFIX + uuid.uuid4().hex[:8]
        coll_name_full = get_full_collection_name(
            chat_state.user_id, coll_name_as_shown
        )

    # If there are uploaded docs, ingest or summarize them
    if docs:
        if message:
            return format_invalid_input_answer(
                "Apologies, you can't simultaneously ingest uploaded files and "
                f"an external resource ({message}).",
                NO_MULTIPLE_INGESTION_SOURCES_STATUS,
            )
        if chat_state.chat_mode == ChatMode.INGEST_COMMAND_ID:
            res = format_nonstreaming_answer(
                "The files you uploaded have been ingested into the collection "
                f"`{coll_name_as_shown}`. If you don't need to ingest "
                "more content into it, rename it with `/db rename my-cool-collection-name`."
            )
        else:
            res = {"answer": summarize(docs, chat_state)}
    else:
        # If no uploaded docs, ingest or summarize the external resource
        fetch_func = get_batch_url_fetcher()  # don't really need the batch aspect here
        html = fetch_func([message])[0]
        link_data = LinkData.from_raw_content(html)

        if link_data.error:
            return format_nonstreaming_answer(
                f"Apologies, I could not retrieve the resource `{message}`."
            )

        docs = [Document(page_content=link_data.text, metadata={"source": message})]

        if chat_state.chat_mode == ChatMode.INGEST_COMMAND_ID:
            # "/ingest https://some.url.com" command - just ingest, don't summarize
            res = format_nonstreaming_answer(
                f"The resource `{message}` has been ingested into the collection "
                f"`{coll_name_as_shown}`. Feel free to ask questions about the collection's "
                "content. If you don't need to ingest "
                "more resources into it, rename it with `/db rename my-cool-collection-name`."
            )
        else:
            res = {"answer": summarize(docs, chat_state)}

    # Ingest into the collection
    coll_metadata = {} if is_new_collection else chat_state.fetch_collection_metadata()
    vectorstore = ingest_into_collection(
        collection_name=coll_name_full,
        docs=docs,
        collection_metadata=coll_metadata,
        chat_state=chat_state,
        is_new_collection=is_new_collection,
    )

    if is_new_collection:
        # Switch to the newly created collection
        res["vectorstore"] = vectorstore

    return res
