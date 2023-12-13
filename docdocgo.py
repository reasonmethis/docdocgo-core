import os
from typing import Any

from langchain.chains import LLMChain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from langchain.chains.question_answering import load_qa_chain
from langchain.vectorstores.base import VectorStoreRetriever

from agents.dbmanager import handle_db_command
from agents.websearcher import (
    WebsearcherData,
    get_iterative_researcher_response,
    get_websearcher_response,
)
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG, load_vectorstore
from components.chroma_ddg_retriever import ChromaDDGRetriever
from components.llm import get_llm, get_prompt_llm_chain
from utils.algo import remove_duplicates_keep_order
from utils.helpers import (
    DEFAULT_MODE,
    DELIMITER,
    HINT_MESSAGE,
    INTRO_ASCII_ART,
    MAIN_BOT_PREFIX,
    extract_chat_mode_from_query,
    parse_query,
    print_no_newline,
)

# Load environment variables
from utils.prepare import (
    DEFAULT_COLLECTION_NAME,
    TEMPERATURE,
    validate_settings,
)
from utils.prompts import (
    CONDENSE_QUESTION_PROMPT,
    JUST_CHAT_PROMPT,
    QA_PROMPT_CHAT,
    QA_PROMPT_QUOTES,
    QA_PROMPT_SUMMARIZE_KB,
)
from utils.type_utils import ChatMode, ChatState, OperationMode


def get_bot_response(chat_state: ChatState):
    command_id = chat_state.command_id
    if command_id == ChatMode.CHAT_WITH_DOCS_COMMAND_ID:  # /docs command
        chat_chain = get_docs_chat_chain(chat_state)
    elif command_id == ChatMode.DETAILS_COMMAND_ID:  # /details command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif command_id == ChatMode.QUOTES_COMMAND_ID:  # /quotes command
        chat_chain = get_docs_chat_chain(chat_state, prompt_qa=QA_PROMPT_QUOTES)
    elif command_id == ChatMode.WEB_COMMAND_ID:  # /web command
        res_from_bot = get_websearcher_response(chat_state)
        return {"answer": res_from_bot["answer"]}  # remove ws_data
    elif command_id == ChatMode.ITERATIVE_RESEARCH_COMMAND_ID:  # /research command
        if chat_state.message:
            # Start new research
            chat_state.ws_data = WebsearcherData.from_query(chat_state.message)
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
    elif command_id == ChatMode.JUST_CHAT_COMMAND_ID:  # /chat command
        chat_chain = get_prompt_llm_chain(
            JUST_CHAT_PROMPT, callbacks=chat_state.callbacks, stream=True
        )
        answer = chat_chain.invoke(
            {"message": chat_state.message, "chat_history": chat_state.chat_history}
        )
        return {"answer": answer}
    elif command_id == ChatMode.DB_COMMAND_ID:  # /db command
        return handle_db_command(chat_state)
    else:
        # Should never happen
        raise ValueError(f"Invalid command id: {command_id}")

    return chat_chain.invoke(
        {
            "question": chat_state.message,
            "chat_history": chat_state.chat_history,
            "search_params": chat_state.search_params,
        }
    )


def get_source_links(result_from_conv_retr_chain: dict[str, Any]) -> list[str]:
    """
    Return a list of source links from the result of a ConversationalRetrievalChain
    """

    source_docs = result_from_conv_retr_chain.get("source_documents", [])

    source_links_with_duplicates = [
        doc.metadata["source"] for doc in source_docs if "source" in doc.metadata
    ]

    # Remove duplicates while keeping order and return
    return remove_duplicates_keep_order(source_links_with_duplicates)


def get_docs_chat_chain(
    chat_state: ChatState,
    prompt_qa=QA_PROMPT_CHAT,
    temperature=None,
    use_sources=False,  # TODO consider removing this
):
    """
    Create a chain to respond to queries using a vectorstore of documents.
    """
    if temperature is None:
        temperature = TEMPERATURE
    llm = get_llm(callbacks=chat_state.callbacks, stream=True)  # main llm
    llm_condense = get_llm(temperature=0)  # condense query

    # Initialize chain for answering queries based on provided doc snippets
    load_chain = load_qa_with_sources_chain if use_sources else load_qa_chain
    PRINT_QA_PROMPT = bool(os.getenv("PRINT_QA_PROMPT"))
    combine_docs_chain = (
        load_chain(llm, prompt=prompt_qa, verbose=PRINT_QA_PROMPT)
        if prompt_qa
        else load_chain(llm, verbose=PRINT_QA_PROMPT)
    )

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

    # Get and return full chain: question generation + doc retrieval + answer generation
    return ChatWithDocsChain(
        question_generator=LLMChain(
            llm=llm_condense,
            prompt=CONDENSE_QUESTION_PROMPT,
            verbose=bool(os.getenv("PRINT_CONDENSE_QUESTION_PROMPT")),
        ),
        retriever=retriever,
        combine_docs_chain=combine_docs_chain,
        return_source_documents=True,
        return_generated_question=True,
    )


def do_intro_tasks():
    print(INTRO_ASCII_ART + "\n\n")

    validate_settings()

    # Load the vector database
    print_no_newline("Loading the vector database of your documents... ")
    vectorstore = load_vectorstore(DEFAULT_COLLECTION_NAME)
    print("Done!")
    return vectorstore


if __name__ == "__main__":
    vectorstore = do_intro_tasks()
    TWO_BOTS = False  # os.getenv("TWO_BOTS", False) # disabled for now

    # Start chat
    print()
    print("Keep in mind:")
    print("- Replies may take several seconds.")
    print('- To exit, type "exit" or "quit", or just enter an empty message twice.')
    print(DELIMITER)
    chat_history = []
    ws_data = None
    while True:
        # Print hints and other info
        if os.getenv("SHOW_HINTS", True):
            print(HINT_MESSAGE)
        print(f"Vector database: {vectorstore.name}\t\tDefault mode: {DEFAULT_MODE}")

        # Get query from user
        query = input("YOU: ")
        if query == "exit" or query == "quit":
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
                    search_params,
                    vectorstore,
                    ws_data,
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

        # Update iterative research data
        if "ws_data" in response:
            ws_data = response["ws_data"]
        # TODO: update in API as well

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
