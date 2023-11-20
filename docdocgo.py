from typing import Any

import sys
import os
import json

from langchain.utilities.google_serper import GoogleSerperAPIWrapper

from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores.base import VectorStore, VectorStoreRetriever

from langchain.chat_models import ChatOpenAI, AzureChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler

from langchain.chains import LLMChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain

from langchain.schema.output_parser import StrOutputParser

# from langchain.chains.conversational_retrieval.prompts import CONDENSE_QUESTION_PROMPT
from utils.prompts import CONDENSE_QUESTION_PROMPT, QA_PROMPT_CHAT, WEBSEARCHER_PROMPT
from utils.prompts import QA_PROMPT_QUOTES, QA_PROMPT_SUMMARIZE_KB
from utils.helpers import DELIMITER, INTRO_ASCII_ART
from utils.helpers import DETAILS_COMMAND_ID, QUOTES_COMMAND_ID, GOOGLE_COMMAND_ID
from utils.helpers import extract_command_id_from_query, parse_query
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG
from components.chroma_ddg_retriever import ChromaDDGRetriever

# Change the working directory in all files to the root of the project
script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)


class CallbackHandlerDDG(BaseCallbackHandler):
    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        print("BOT: ", end="", flush=True)

    def on_llm_new_token(self, token, **kwargs) -> None:
        print(token, end="", flush=True)

    def on_retry(self, *args, **kwargs):
        print(f"ON_RETRY: \nargs = {args}\nkwargs = {kwargs}")


def get_bot_response(message, chat_history, search_params, command_id):
    if command_id == DETAILS_COMMAND_ID:  # /details command
        bot = create_bot(vectorstore, prompt_qa=QA_PROMPT_SUMMARIZE_KB)
    elif command_id == QUOTES_COMMAND_ID:  # /quotes command
        bot = create_bot(vectorstore, prompt_qa=QA_PROMPT_QUOTES)
    elif command_id == GOOGLE_COMMAND_ID:  # /google command
        return get_websearcher_response(message)
    else:
        bot = create_bot(vectorstore)

    return bot(
        {
            "question": message,
            "chat_history": chat_history,
            "search_params": search_params,
        }
    )


def get_source_links(result_from_conv_retr_chain):
    """Returns a list of source links from the result of a ConversationalRetrievalChain"""

    source_docs = result_from_conv_retr_chain.get("source_documents", [])

    source_links_with_duplicates = [
        doc.metadata["source"] for doc in source_docs if "source" in doc.metadata
    ]

    # Remove duplicates while keeping order
    return list(dict.fromkeys(source_links_with_duplicates))


def get_llm(temperature=None, print_streamed=False):
    """Returns an LLM instance (either AzureChatOpenAI or ChatOpenAI, depending
    on the value of IS_AZURE)"""
    if temperature is None:
        temperature = TEMPERATURE
    callbacks = [CallbackHandlerDDG()] if print_streamed else []
    if IS_AZURE:
        llm = AzureChatOpenAI(
            deployment_name=CHAT_DEPLOYMENT_NAME,
            temperature=temperature,
            request_timeout=LLM_REQUEST_TIMEOUT,
            streaming=True,
            callbacks=callbacks,
        )
    else:
        llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=temperature,
            request_timeout=LLM_REQUEST_TIMEOUT,
            streaming=True,
            callbacks=callbacks,
        )
    return llm


def get_websearcher_response(message: str):
    search = GoogleSerperAPIWrapper()
    search_results = search.results(message)
    json_results = json.dumps(search_results, indent=4)

    chain = WEBSEARCHER_PROMPT | get_llm(print_streamed=True) | StrOutputParser()
    answer = chain.invoke({"results": json_results, "query": message})
    return {"answer": answer}


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
        llm = get_llm(print_streamed=True)  # main llm
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


print(INTRO_ASCII_ART + "\n\n")

IS_AZURE = bool(os.getenv("OPENAI_API_BASE"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

VECTORDB_DIR = os.getenv("VECTORDB_DIR")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))

# Check that the necessary environment variables are set
if (IS_AZURE and not (EMBEDDINGS_DEPLOYMENT_NAME and CHAT_DEPLOYMENT_NAME)) or (
    not IS_AZURE and not os.getenv("OPENAI_API_KEY")
):
    print("Please set the environment variables in .env, as shown in .env.example.")
    sys.exit()

# Verify the validity of the db path
if not VECTORDB_DIR or not os.path.isdir(VECTORDB_DIR):
    print(
        "You have not specified a valid directory for the vector database. "
        "If you have not created one yet, please do so by ingesting your "
        "documents, as described in the README. If you have already done so,"
        "then set the VECTORDB_DIR environment variable to the vector database directory."
    )
    sys.exit()

# Load the vector database
print("Loading the vector database of your documents... ", end="", flush=True)
vectorstore = ChromaDDG(
    embedding_function=OpenAIEmbeddings(), persist_directory=VECTORDB_DIR
)
print("Done!")

if __name__ == "__main__":
    TWO_BOTS = False  # os.getenv("TWO_BOTS", False) # disabled for now

    # Start chat
    print()
    print("Keep in mind:")
    print("- Replies may take several seconds.")
    print('- To exit, type "exit" or "quit", or just enter an empty message twice.')
    print(DELIMITER)
    chat_history = []
    while True:
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

        # Get response from bot
        try:
            result = get_bot_response(query, chat_history, search_params, command_id)
        except Exception as e:
            print("<Apologies, an error has occurred>")
            print("ERROR:", e)
            print(DELIMITER)
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
