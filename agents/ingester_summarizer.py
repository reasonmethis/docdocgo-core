from langchain.schema import Document

from agents.dbmanager import construct_full_collection_name
from components.llm import get_prompt_llm_chain
from utils.chat_state import ChatState
from utils.docgrab import ingest_docs_into_chroma
from utils.helpers import INGESTED_DOCS_INIT_COLL_NAME, format_nonstreaming_answer
from utils.lang_utils import limit_tokens_in_text
from utils.prepare import CONTEXT_LENGTH
from utils.prompts import SUMMARIZER_PROMPT
from utils.type_utils import ChatMode
from utils.web import LinkData, get_batch_url_fetcher

DEFAULT_MAX_TOKENS_FINAL_CONTEXT = int(CONTEXT_LENGTH * 0.7)


def get_ingester_summarizer_response(chat_state: ChatState):
    message = chat_state.parsed_query.message
    fetcher = get_batch_url_fetcher()  # don't really need the batch aspect here
    html = fetcher([message])[0]
    link_data = LinkData.from_raw_content(html)

    if link_data.error:
        return format_nonstreaming_answer(
            f"Apologies, I could not retrieve the resource `{message}`."
        )

    if chat_state.chat_mode == ChatMode.INGEST_COMMAND_ID:
        # "/ingest https://some.url.com" command - just ingest, don't summarize
        res = format_nonstreaming_answer(
            f"The resource `{message}` has been ingested into the collection "
            f"`{INGESTED_DOCS_INIT_COLL_NAME}`. If you don't need to ingest "
            "more content into it, rename it by with `/db rename my-cool-collection-name`."
        )
    else:
        # "/summarize https://some.url.com" command
        summarizer_chain = get_prompt_llm_chain(
            SUMMARIZER_PROMPT,
            llm_settings=chat_state.bot_settings,
            api_key=chat_state.openai_api_key,
            callbacks=chat_state.callbacks,
            # streaming=False,
        )

        text, num_tokens = limit_tokens_in_text(
            link_data.text, DEFAULT_MAX_TOKENS_FINAL_CONTEXT
        )

        if text != link_data.text:
            text += "\n\nNOTE: The above content was truncated to fit the maximum token limit."

        res = {"answer": summarizer_chain.invoke({"content": text})}

    # Ingest into Chroma
    doc = Document(page_content=link_data.text, metadata={"source": message})
    coll_name_full = construct_full_collection_name(
        chat_state.user_id, INGESTED_DOCS_INIT_COLL_NAME
    )
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
