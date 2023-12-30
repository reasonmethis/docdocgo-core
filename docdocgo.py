import os
from typing import Any

from langchain.chains import LLMChain
from langchain.vectorstores.base import VectorStoreRetriever

from _prepare_env import is_env_loaded
from agents.dbmanager import handle_db_command
from agents.websearcher import (
    get_iterative_researcher_response,
    get_websearcher_response,
)
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG, load_vectorstore
from components.chroma_ddg_retriever import ChromaDDGRetriever
from components.llm import get_llm, get_prompt_llm_chain
from utils.algo import remove_duplicates_keep_order
from utils.chat_state import ChatState
from utils.helpers import (
    DEFAULT_MODE,
    DELIMITER,
    HELP_MESSAGE,
    INTRO_ASCII_ART,
    MAIN_BOT_PREFIX,
    extract_chat_mode_from_query,
    parse_query,
    print_no_newline,
)
from utils.lang_utils import pairwise_chat_history_to_msg_list

# Load environment variables
from utils.prepare import (
    DEFAULT_COLLECTION_NAME,
)
from utils.prompts import (
    CHAT_WITH_DOCS_PROMPT,
    CONDENSE_QUESTION_PROMPT,
    JUST_CHAT_PROMPT,
    QA_PROMPT_QUOTES,
    QA_PROMPT_SUMMARIZE_KB,
)
from utils.type_utils import ChatMode, OperationMode


def get_bot_response(chat_state: ChatState):
    chat_mode = chat_state.chat_mode
    if chat_mode == ChatMode.CHAT_WITH_DOCS_COMMAND_ID:  # /docs command
        chat_chain = get_docs_chat_chain(chat_state)
    elif chat_mode == ChatMode.DETAILS_COMMAND_ID:  # /details command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif chat_mode == ChatMode.QUOTES_COMMAND_ID:  # /quotes command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_QUOTES)
    elif chat_mode == ChatMode.WEB_COMMAND_ID:  # /web command
        return get_websearcher_response(chat_state)
        # return {"answer": res_from_bot["answer"]}  # remove ws_data
    elif chat_mode == ChatMode.ITERATIVE_RESEARCH_COMMAND_ID:  # /research command
        if chat_state.message:
            # Start new research
            # chat_state.ws_data = WebsearcherData.from_query(chat_state.message)
            pass
        elif not chat_state.ws_data:
            return {
                "answer": "The /research prefix without a message is used to iterate "
                "on the previous report. However, there is no previous report.",
                "needs_print": True,
            }
        # Get response from iterative researcher
        res_from_bot = get_iterative_researcher_response(chat_state)
        ws_data = res_from_bot["ws_data"]  # res_from_bot also contains "answer"

        # Load the new vectorstore if needed
        partial_res = {}
        if ws_data.collection_name != chat_state.vectorstore.name:
            vectorstore = load_vectorstore(
                ws_data.collection_name, chat_state.vectorstore._client
            )
            partial_res["vectorstore"] = vectorstore

        # Return response, including the new vectorstore if needed
        return partial_res | res_from_bot
    elif chat_mode == ChatMode.JUST_CHAT_COMMAND_ID:  # /chat command
        chat_chain = get_prompt_llm_chain(
            JUST_CHAT_PROMPT,
            llm_settings=chat_state.bot_settings,
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
    elif chat_mode == ChatMode.DB_COMMAND_ID:  # /db command
        return handle_db_command(chat_state)
    elif chat_mode == ChatMode.HELP_COMMAND_ID:  # /help command
        return {"answer": HELP_MESSAGE}
    else:
        # Should never happen
        raise ValueError(f"Invalid command id: {chat_mode}")

    return chat_chain.invoke(
        {
            "question": chat_state.message,
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
        return sources_with_duplicates # return empty list

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
    query_generator_chain = LLMChain(
        llm=get_llm(chat_state.bot_settings.model_copy(update={"temperature": 0})),
        prompt=CONDENSE_QUESTION_PROMPT,
        verbose=bool(os.getenv("PRINT_CONDENSE_QUESTION_PROMPT")),
    )  # need it to be an object that exposes easy access to the underlying llm

    # Initialize retriever from the provided vectorstore
    if isinstance(chat_state.vectorstore, ChromaDDG):
        retriever = ChromaDDGRetriever(
            vectorstore=chat_state.vectorstore,
            search_type="similarity_ddg",
            verbose=bool(os.getenv("PRINT_SIMILARITIES")),
        )
    else:
        retriever = VectorStoreRetriever(vectorstore=chat_state.vectorstore)
        # search_kwargs={
        #     "k": num_docs_max,
        #     "score_threshold": relevance_threshold,
        # },

    # Initialize chain for answering queries based on provided doc snippets
    qa_from_docs_chain = get_prompt_llm_chain(
        prompt_qa,
        llm_settings=chat_state.bot_settings,
        print_prompt=bool(os.getenv("PRINT_QA_PROMPT")),
        callbacks=chat_state.callbacks,
        stream=True,
    )

    # Get and return full chain: question generation + doc retrieval + answer generation
    return ChatWithDocsChain(
        query_generator_chain=query_generator_chain,
        retriever=retriever,
        qa_from_docs_chain=qa_from_docs_chain,
        return_source_documents=True,
        return_generated_question=True,
    )


def do_intro_tasks():
    print(INTRO_ASCII_ART + "\n\n")

    # validate_settings()

    # Load the vector database
    print_no_newline("Loading the vector database of your documents... ")
    try:
        vectorstore = load_vectorstore(DEFAULT_COLLECTION_NAME)
    except Exception as e:
        print(
            f"Failed to load the vector database. Please check the settings. Error: {e}"
        )
        raise ValueError(
            f"Could not load the default document collection {DEFAULT_COLLECTION_NAME}."
        )
    print("Done!")
    return vectorstore


if __name__ == "__main__":
    vectorstore = do_intro_tasks()
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

        # Parse the query to extract command id & search params, if any
        query, command_id = extract_chat_mode_from_query(query)
        query, search_params = parse_query(query)

        # Get response from the bot
        try:
            response = get_bot_response(
                ChatState(
                    OperationMode.CONSOLE,
                    command_id,
                    query,
                    chat_history,
                    None,  # sources_history (NOTE: not used in console mode for now)
                    chat_history,  # chat_and_command_history is not used in console mode
                    search_params,
                    vectorstore,  # callbacks and bot_settings can be default here
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
            chat_history.append((query, answer))

        # Update vectorstore if needed
        if "vectorstore" in response:
            vectorstore = response["vectorstore"]

        # Get sources
        # TODO: also get sources from the websearcher
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
