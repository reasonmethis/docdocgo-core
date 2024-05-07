import os
from typing import Any

from langchain.chains import LLMChain

from _prepare_env import is_env_loaded
from agents.dbmanager import get_user_facing_collection_name, handle_db_command
from agents.exporter import get_exporter_response
from agents.ingester_summarizer import get_ingester_summarizer_response
from agents.researcher import get_researcher_response, get_websearcher_response
from agents.share_manager import handle_share_command
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG, load_vectorstore
from components.chroma_ddg_retriever import ChromaDDGRetriever
from components.llm import get_llm, get_llm_from_prompt_llm_chain, get_prompt_llm_chain
from utils.algo import remove_duplicates_keep_order
from utils.chat_state import ChatState
from utils.helpers import (
    DEFAULT_MODE,
    DELIMITER,
    HELP_MESSAGE,
    INTRO_ASCII_ART,
    MAIN_BOT_PREFIX,
    print_no_newline,
)
from utils.lang_utils import pairwise_chat_history_to_msg_list

# Load environment variables
from utils.prepare import DEFAULT_COLLECTION_NAME, get_logger
from utils.prompts import (
    CHAT_WITH_DOCS_PROMPT,
    CONDENSE_QUESTION_PROMPT,
    JUST_CHAT_PROMPT,
    QA_PROMPT_QUOTES,
    QA_PROMPT_SUMMARIZE_KB,
)
from utils.query_parsing import parse_query
from utils.type_utils import ChatMode, OperationMode

logger = get_logger()

default_vectorstore = None  # can move to chat_state


def get_bot_response(chat_state: ChatState):
    global default_vectorstore
    chat_mode_val = chat_state.chat_mode.value # use value due to Streamlit code reloading
    if chat_mode_val == ChatMode.CHAT_WITH_DOCS_COMMAND_ID.value:  # /docs command
        chat_chain = get_docs_chat_chain(chat_state)
    elif chat_mode_val == ChatMode.DETAILS_COMMAND_ID.value:  # /details command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif chat_mode_val == ChatMode.QUOTES_COMMAND_ID.value:  # /quotes command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_QUOTES)
    elif chat_mode_val == ChatMode.WEB_COMMAND_ID.value:  # /web command
        return get_websearcher_response(chat_state)
    elif chat_mode_val == ChatMode.SUMMARIZE_COMMAND_ID.value:  # /summarize command
        return get_ingester_summarizer_response(chat_state)
    elif chat_mode_val == ChatMode.RESEARCH_COMMAND_ID.value:  # /research command
        return get_researcher_response(chat_state)  # includes "vectorstore" if created
    elif chat_mode_val == ChatMode.JUST_CHAT_COMMAND_ID.value:  # /chat command
        chat_chain = get_prompt_llm_chain(
            JUST_CHAT_PROMPT,
            llm_settings=chat_state.bot_settings,
            api_key=chat_state.openai_api_key,
            callbacks=chat_state.callbacks,
            stream=True,
        )
        answer = chat_chain.invoke(
            {
                "message": chat_state.message,
                "chat_history": pairwise_chat_history_to_msg_list(
                    chat_state.chat_history
                ),
            }
        )
        return {"answer": answer}
    elif chat_mode_val == ChatMode.DB_COMMAND_ID.value:  # /db command
        return handle_db_command(chat_state)
    elif chat_mode_val == ChatMode.SHARE_COMMAND_ID.value:  # /share command
        return handle_share_command(chat_state)
    elif chat_mode_val == ChatMode.HELP_COMMAND_ID.value:  # /help command
        if not chat_state.parsed_query.message:
            return {"answer": HELP_MESSAGE, "needs_print": True}

        # Temporarily switch to the default vectorstore to get help
        saved_vectorstore = chat_state.vectorstore
        if default_vectorstore is None:  # can happen due to Streamlit's code reloading
            default_vectorstore = chat_state.get_new_vectorstore(
                DEFAULT_COLLECTION_NAME
            )
        chat_state.vectorstore = default_vectorstore
        chat_chain = get_docs_chat_chain(chat_state)
        res = chat_chain.invoke(
            {
                "question": chat_state.message,
                "coll_name": DEFAULT_COLLECTION_NAME,
                "chat_history": chat_state.chat_history,
            }
        )
        chat_state.vectorstore = saved_vectorstore
        return res
    elif chat_mode_val == ChatMode.INGEST_COMMAND_ID.value:  # /ingest command
        # If a URL is given, fetch and ingest it. Otherwise, upload local docs
        if (
            chat_state.operation_mode.value == OperationMode.CONSOLE.value
            and not chat_state.parsed_query.message
        ):
            # NOTE: "value" is needed because OperationMode, ChromaDDG, etc. sometimes
            # get imported twice (I think when Streamlit reloads the code).
            return {
                "answer": "Sorry, the /ingest command with no URL is not supported "
                "in console mode. Please run `python ingest_local_docs.py`."
            }
        return get_ingester_summarizer_response(chat_state)
    elif chat_mode_val == ChatMode.EXPORT_COMMAND_ID.value:  # /export command
        return get_exporter_response(chat_state)
    else:
        # Should never happen
        raise ValueError(f"Invalid chat mode: {chat_state.chat_mode}")

    return chat_chain.invoke(
        {
            "question": chat_state.message,
            "coll_name": get_user_facing_collection_name(
                chat_state.user_id, chat_state.vectorstore.name
            ),
            "chat_history": chat_state.chat_history,
            "search_params": chat_state.search_params,
        }
    )


def get_source_links(result_from_chain: dict[str, Any]) -> list[str]:
    """
    Return a list of source links from the result of a chat chain.
    """

    source_docs = result_from_chain.get("source_documents", [])

    sources_with_duplicates = [
        doc.metadata["source"] for doc in source_docs if "source" in doc.metadata
    ]

    sources_with_duplicates += result_from_chain.get("source_links", [])

    # For performance
    if not sources_with_duplicates:
        return sources_with_duplicates  # return empty list

    # Remove duplicates while keeping order and return
    return remove_duplicates_keep_order(sources_with_duplicates)


def get_docs_chat_chain(
    chat_state: ChatState,
    prompt_qa=CHAT_WITH_DOCS_PROMPT,
):
    """
    Create a chain to respond to queries using a vectorstore of documents.
    """
    # Initialize chain for query generation from chat history
    llm_for_q_generation = get_llm(
        settings=chat_state.bot_settings.model_copy(update={"temperature": 0}),
        api_key=chat_state.openai_api_key,
    )
    query_generator_chain = LLMChain(
        llm=llm_for_q_generation,
        prompt=CONDENSE_QUESTION_PROMPT,
        verbose=bool(os.getenv("PRINT_CONDENSE_QUESTION_PROMPT")),
    )  # need it to be an object that exposes easy access to the underlying llm

    # Initialize retriever from the provided vectorstore
    if not isinstance(chat_state.vectorstore, ChromaDDG):
        type_str = str(type(chat_state.vectorstore))
        if not type_str.endswith("ChromaDDG'>"):
            raise ValueError("Invalid vectorstore type: " + type_str)
        print(
            "WARNING: unusual case where vectorstore is not identified as an "
            "instance of ChromaDDG, but its type is: " + type_str
        )

    retriever = ChromaDDGRetriever(
        vectorstore=chat_state.vectorstore,
        search_type="similarity_ddg",
        llm_for_token_counting=None,  # will be assigned in a moment
        verbose=bool(os.getenv("PRINT_SIMILARITIES")),
    )
    # retriever = VectorStoreRetriever(vectorstore=chat_state.vectorstore)
    # search_kwargs={
    #     "k": num_docs_max,
    #     "score_threshold": relevance_threshold,
    # },

    # Initialize chain for answering queries based on provided doc snippets
    qa_from_docs_chain = get_prompt_llm_chain(
        prompt_qa,
        llm_settings=chat_state.bot_settings,
        api_key=chat_state.openai_api_key,
        callbacks=chat_state.callbacks,
        print_prompt=bool(os.getenv("PRINT_QA_PROMPT")),
        stream=True,
    )

    # Assign llm_for_token_counting for the retriever
    # if isinstance(chat_state.vectorstore, ChromaDDG):
    llm_for_response = get_llm_from_prompt_llm_chain(qa_from_docs_chain)
    retriever.llm_for_token_counting = llm_for_response

    # Get and return full chain: question generation + doc retrieval + answer generation
    return ChatWithDocsChain(
        query_generator_chain=query_generator_chain,
        retriever=retriever,
        qa_from_docs_chain=qa_from_docs_chain,
        return_source_documents=True,
        return_generated_question=True,
    )


def do_intro_tasks(
    openai_api_key: str, collection_name: str | None = None
) -> ChromaDDG:
    global default_vectorstore

    print(INTRO_ASCII_ART + "\n\n")
    print_no_newline("Loading the vector database of your documents... ")

    # Load and save default vector store
    try:
        vectorstore = default_vectorstore = load_vectorstore(
            DEFAULT_COLLECTION_NAME, openai_api_key=openai_api_key
        )
    except Exception as e:
        print(
            f"Failed to load the vector database. Please check the settings. Error: {e}"
        )
        raise ValueError(
            f"Could not load the default document collection {repr(DEFAULT_COLLECTION_NAME)}."
        )

    # Load vectorstore for passed collection name
    # NOTE/TODO: This is not used in the current version of the code
    if collection_name:
        try:
            vectorstore = load_vectorstore(
                collection_name, openai_api_key=openai_api_key
            )
        except Exception as e:
            print(
                f"Failed to load the {repr(collection_name)} collection. Error: {e}\n"
            )

    print("Done!")
    return vectorstore


if __name__ == "__main__":
    vectorstore = do_intro_tasks(os.getenv("DEFAULT_OPENAI_API_KEY", ""))
    TWO_BOTS = False  # os.getenv("TWO_BOTS", False) # disabled for now

    # Start chat
    chat_history = []
    while True:
        # Print hints and other info
        print(
            'Type "/help" for help, "exit" to exit (or just press Enter twice)\n'
            f"Document collection: {vectorstore.name} ({vectorstore.collection.count()} "
            f"doc chunks)\t\tDefault mode: {DEFAULT_MODE}"
        )
        print(DELIMITER)

        # Get query from user
        query = input("\nYOU: ")
        if query.strip() in {"exit", "/exit", "quit", "/quit"}:
            break
        if query == "":
            print("Please enter your query or press Enter to exit.")
            query = input("YOU: ")
            if query == "":
                break
        print()

        # Parse the query
        parsed_query = parse_query(query)

        # Get response from the bot
        try:
            response = get_bot_response(
                ChatState(
                    operation_mode=OperationMode.CONSOLE,
                    parsed_query=parsed_query,
                    chat_history=chat_history,
                    vectorstore=vectorstore,  # callbacks and bot_settings can be default here
                    openai_api_key=os.getenv("DEFAULT_OPENAI_API_KEY", ""),
                )
            )
        except Exception as e:
            print("<Apologies, an error has occurred>")
            print("ERROR:", e)
            print(DELIMITER)
            if os.getenv("RERAISE_EXCEPTIONS"):
                raise e
            continue
        answer = response["answer"]

        # Print reply if it wasn't streamed
        if response.get("needs_print", False):
            print(MAIN_BOT_PREFIX + answer)
        print("\n" + DELIMITER)

        # Update chat history if needed
        if answer:
            chat_history.append((parsed_query.message, answer))

        # Update vectorstore if needed
        if "vectorstore" in response:
            vectorstore = response["vectorstore"]

        # Get sources
        # TODO: also get sources from the researcher
        source_links = get_source_links(response)
        if source_links:
            print("Sources:")
            print(*source_links, sep="\n")
            print(DELIMITER)

        # Print standalone query if needed
        if os.getenv("PRINT_STANDALONE_QUERY") and "generated_question" in response:
            print(f"Standalone query: {response['generated_question']}")
            print(DELIMITER)

# This snippet is merely to make sure that Ruff or other tools don't remove the
# _prepare_env import above, which is needed to set up the environment variables
# and do other initialization tasks before other imports are done.
if not is_env_loaded:
    raise RuntimeError("This should be unreachable.")
