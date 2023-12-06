import os
from typing import Any

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores.base import VectorStore, VectorStoreRetriever

from langchain.chains import LLMChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain
from utils.algo import remove_duplicates_keep_order

# from langchain.chains.conversational_retrieval.prompts import CONDENSE_QUESTION_PROMPT
from utils.prepare import validate_settings, VECTORDB_DIR, TEMPERATURE  # loads env vars
from utils.prompts import CONDENSE_QUESTION_PROMPT, JUST_CHAT_PROMPT, QA_PROMPT_CHAT
from utils.prompts import QA_PROMPT_QUOTES, QA_PROMPT_SUMMARIZE_KB
from utils.helpers import (
    CHAT_WITH_DOCS_COMMAND_ID,
    DEFAULT_MODE,
    DELIMITER,
    INTRO_ASCII_ART,
    HINT_MESSAGE,
    ITERATIVE_RESEARCH_COMMAND_ID,
    JUST_CHAT_COMMAND_ID,
    MAIN_BOT_PREFIX,
    SWITCH_DB_COMMAND_ID,
    print_no_newline,
)
from utils.helpers import DETAILS_COMMAND_ID, QUOTES_COMMAND_ID, WEB_COMMAND_ID
from utils.helpers import extract_command_id_from_query, parse_query
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG
from components.chroma_ddg_retriever import ChromaDDGRetriever
from components.llm import get_llm, get_prompt_llm_chain
from agents.websearcher import (
    get_iterative_researcher_response,
    get_websearcher_response,
    WebsearcherData,
)


def get_bot_response(
    message, chat_history, search_params, command_id, vectorstore, ws_data=None
):
    if command_id == CHAT_WITH_DOCS_COMMAND_ID:  # /docs command
        chat_chain = get_docs_chat_chain(vectorstore)
    elif command_id == DETAILS_COMMAND_ID:  # /details command
        chat_chain = get_docs_chat_chain(vectorstore, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif command_id == QUOTES_COMMAND_ID:  # /quotes command
        chat_chain = get_docs_chat_chain(vectorstore, prompt_qa=QA_PROMPT_QUOTES)
    elif command_id == WEB_COMMAND_ID:  # /web command
        return get_websearcher_response(message)
    elif command_id == ITERATIVE_RESEARCH_COMMAND_ID:  # /research command
        if message:
            # Start new research
            ws_data = WebsearcherData.from_query(message)
        elif not ws_data:
            return {
                "answer": "The /research prefix without a message is used to iterate "
                "on the previous report. However, there is no previous report.",
                "needs_print": True,
            }
        # Get response from iterative researcher
        ws_data = get_iterative_researcher_response(ws_data)
        return {"answer": ws_data.report, "ws_data": ws_data}
    elif command_id == JUST_CHAT_COMMAND_ID:  # /chat command
        chat_chain = get_prompt_llm_chain(JUST_CHAT_PROMPT, stream=True)
        answer = chat_chain.invoke({"message": message, "chat_history": chat_history})
        return {"answer": answer}
    elif command_id == SWITCH_DB_COMMAND_ID:  # /db command
        vectorstore_path = message.strip()
        stem = {"needs_print": True}
        if not vectorstore_path:
            return stem | {"answer": "A vector database path must be provided."}
        try:
            vectorstore, vectorstore_name = load_vectorstore(vectorstore_path)
        except Exception as e:
            return stem | {
                "answer": f"Error loading requested vector database: {e}",
            }
        return stem | {
            "answer": f"Switching to vector database: {vectorstore_path}",
            "vectorstore_name": vectorstore_name,
            "vectorstore": vectorstore,
        }
    else:
        # Should never happen
        raise ValueError(f"Invalid command id: {command_id}")

    return chat_chain.invoke(
        {
            "question": message,
            "chat_history": chat_history,
            "search_params": search_params,
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
    vectorstore: VectorStore,  # NOTE in our case, this is a ChromaDDG vectorstore
    prompt_qa=QA_PROMPT_CHAT,
    temperature=None,
    use_sources=False,  # TODO consider removing this
):
    """
    Create a chain to respond to queries using a vectorstore of documents.
    """
    if temperature is None:
        temperature = TEMPERATURE
    llm = get_llm(stream=True)  # main llm
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
    if isinstance(vectorstore, ChromaDDG):
        retriever = ChromaDDGRetriever(
            vectorstore=vectorstore,
            search_type="similarity_ddg",
            verbose=bool(os.getenv("PRINT_SIMILARITIES")),
        )
    else:
        retriever = VectorStoreRetriever(vectorstore=vectorstore)
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


def load_vectorstore(path: str):
    """
    Load a ChromaDDG vectorstore from a given path.
    """
    if not os.path.isdir(path):
        raise ValueError(f"Invalid vectorstore path: {path}")
    vectorstore = ChromaDDG(
        embedding_function=OpenAIEmbeddings(), persist_directory=path
    )
    vectorstore_name = os.path.basename(path)
    return vectorstore, vectorstore_name


def do_intro_tasks():
    print(INTRO_ASCII_ART + "\n\n")

    validate_settings()

    # Load the vector database
    print_no_newline("Loading the vector database of your documents... ")
    vectorstore, vectorstore_name = load_vectorstore(VECTORDB_DIR)
    print("Done!")
    return vectorstore, vectorstore_name


if __name__ == "__main__":
    vectorstore, vectorstore_name = do_intro_tasks()
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
        print(f"Vector database: {vectorstore_name}\t\tDefault mode: {DEFAULT_MODE}")

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
        query, command_id = extract_command_id_from_query(query)
        query, search_params = parse_query(query)

        # Get response from the bot
        try:
            response = get_bot_response(
                query, chat_history, search_params, command_id, vectorstore, ws_data
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

        # Update chat history
        chat_history.append((query, answer))

        # Update iterative research data
        if "ws_data" in response:
            ws_data = response["ws_data"]
        # TODO: update in API as well

        # Update vectorstore if needed
        if "vectorstore" in response:
            vectorstore = response["vectorstore"]
            vectorstore_name = response["vectorstore_name"]

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
