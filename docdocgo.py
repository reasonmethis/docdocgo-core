import sys
import os

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
    DELIMITER,
    INTRO_ASCII_ART,
    HINT_MESSAGE,
    ITERATIVE_RESEARCH_COMMAND_ID,
    JUST_CHAT_COMMAND_ID,
)
from utils.helpers import DETAILS_COMMAND_ID, QUOTES_COMMAND_ID, WEB_COMMAND_ID
from utils.helpers import extract_command_id_from_query, parse_query
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG
from components.chroma_ddg_retriever import ChromaDDGRetriever
from components.llm import get_llm, get_prompt_llm_chain
from agents.websearcher import (
    get_websearcher_iterative_response,
    get_websearcher_response,
    IterativeWebsearcherData,
)


def get_bot_response(
    message, chat_history, search_params, command_id, vectorstore, ws_data=None
):
    if command_id == DETAILS_COMMAND_ID:  # /details command
        chat_chain = create_bot(vectorstore, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif command_id == QUOTES_COMMAND_ID:  # /quotes command
        chat_chain = create_bot(vectorstore, prompt_qa=QA_PROMPT_QUOTES)
    elif command_id == WEB_COMMAND_ID:  # /web command
        return get_websearcher_response(message)
    elif command_id == ITERATIVE_RESEARCH_COMMAND_ID:  # /research command
        if message:
            # Start new research
            ws_data = IterativeWebsearcherData.from_query(message)
        elif not ws_data:
            return {
                "answer": "The /research prefix without a message is used to iterate "
                "on the previous report. However, there is no previous report."
            }
        # Get response from iterative researcher
        ws_data = get_websearcher_iterative_response(ws_data)
        return {"answer": ws_data.report, "ws_data": ws_data}
    elif command_id == JUST_CHAT_COMMAND_ID:  # /chat command
        chat_chain = get_prompt_llm_chain(JUST_CHAT_PROMPT, stream=True)
        answer = chat_chain.invoke({"message": message, "chat_history": chat_history})
        return {"answer": answer}
    else:
        chat_chain = create_bot(vectorstore)

    return chat_chain(
        {
            "question": message,
            "chat_history": chat_history,
            "search_params": search_params,
        }
    )


def get_source_links(result_from_conv_retr_chain):
    """
    Returns a list of source links from the result of a ConversationalRetrievalChain
    """

    source_docs = result_from_conv_retr_chain.get("source_documents", [])

    source_links_with_duplicates = [
        doc.metadata["source"] for doc in source_docs if "source" in doc.metadata
    ]

    # Remove duplicates while keeping order and return
    return remove_duplicates_keep_order(source_links_with_duplicates)


def create_bot(
    vectorstore: VectorStore,  # NOTE in our case, this is a ChromaDDG vectorstore
    prompt_qa=QA_PROMPT_CHAT,
    temperature=None,
    use_sources=False,  # TODO consider removing this
):
    """Creates a chain that can respond to queries using a vectorstore of documents."""
    if temperature is None:
        temperature = TEMPERATURE
    try:
        llm = get_llm(stream=True)  # main llm
        llm_condense = get_llm(
            temperature=0
        )  # condense query (0 to have reliable rephrasing)

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

        # Initialize full chain: question generation + doc retrieval + answer generation
        bot = ChatWithDocsChain(
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
        return bot
    except Exception as e:
        print(e)
        sys.exit()


def do_intro_tasks():
    print(INTRO_ASCII_ART + "\n\n")

    validate_settings()

    # Load the vector database
    print("Loading the vector database of your documents... ", end="", flush=True)
    vectorstore = ChromaDDG(
        embedding_function=OpenAIEmbeddings(), persist_directory=VECTORDB_DIR
    )
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
        # Get query from user
        if os.getenv("SHOW_HINTS", True):
            print(HINT_MESSAGE)
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

        # Get response from bot
        try:
            result = get_bot_response(
                query, chat_history, search_params, command_id, vectorstore, ws_data
            )
        except Exception as e:
            print("<Apologies, an error has occurred>")
            print("ERROR:", e)
            print(DELIMITER)
            if os.getenv("RERAISE_EXCEPTIONS"):
                raise e
            continue

        answer = result["answer"]

        # Print reply
        # print(f"AI: {reply}") - no need, it's streamed to stdout now
        print()
        print(DELIMITER)

        # if TWO_BOTS:
        #     result2 = bot2({"question": query, "chat_history": chat_history})
        #     reply2 = result2["answer"]
        #     print()
        #     print(f"AI2: {reply2}")
        #     print(DELIMITER)

        # Update chat history
        chat_history.append((query, answer))

        # Update iterative research data
        if "ws_data" in result:
            ws_data = result["ws_data"]
        # TODO: update in API as well

        # Get sources
        source_links = get_source_links(result)
        if source_links:
            print("Sources:")
            print(*source_links, sep="\n")
            print(DELIMITER)

        # Print standalone query if needed
        if os.getenv("PRINT_STANDALONE_QUERY") and "generated_question" in result:
            print(f"Standalone query: {result['generated_question']}")
            print(DELIMITER)
