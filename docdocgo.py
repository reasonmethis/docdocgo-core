import sys
import os

from langchain.document_loaders import TextLoader, DirectoryLoader
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores.base import VectorStore, VectorStoreRetriever

from langchain.chat_models import ChatOpenAI, AzureChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler

from langchain.chains import LLMChain
from langchain.chains.question_answering import load_qa_chain
from langchain.chains.qa_with_sources import load_qa_with_sources_chain

# from langchain.chains.conversational_retrieval.prompts import CONDENSE_QUESTION_PROMPT
from utils.prompts import CONDENSE_QUESTION_PROMPT, QA_PROMPT_CHAT
from utils.helpers import DELIMITER, INTRO_ASCII_ART, parse_query
from components.chat_with_docs_chain import ChatWithDocsChain
from components.chroma_ddg import ChromaDDG
from components.chroma_ddg_retriever import ChromaDDGRetriever
from utils import docgrab

VERBOSE = False

# Change the working directory in all files to the root of the project
script_directory = os.path.dirname(os.path.abspath(__file__))
os.chdir(script_directory)


class CallbackHandlerDDG(BaseCallbackHandler):
    def on_llm_new_token(self, token, **kwargs) -> None:
        print(token, end="", flush=True)

    def on_retry(self, *args, **kwargs):
        print(f"ON_RETRY: \nargs = {args}\nkwargs = {kwargs}")


def get_source_links(result_from_conv_retr_chain):
    """Returns a list of source links from the result of a ConversationalRetrievalChain"""

    source_docs = result_from_conv_retr_chain.get("source_documents", [])

    source_links_with_duplicates = [
        doc.metadata["source"] for doc in source_docs if "source" in doc.metadata
    ]

    # Remove duplicates while keeping order
    return list(dict.fromkeys(source_links_with_duplicates))


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
        if IS_AZURE:
            llm = AzureChatOpenAI(
                deployment_name=CHAT_DEPLOYMENT_NAME,
                temperature=temperature,
                request_timeout=LLM_REQUEST_TIMEOUT,
                streaming=True,
                callbacks=[CallbackHandlerDDG()],
            )  # main llm
            llm_condense = AzureChatOpenAI(
                deployment_name=CHAT_DEPLOYMENT_NAME,
                temperature=0,  # 0 to have reliable rephrasing
                request_timeout=LLM_REQUEST_TIMEOUT,
                streaming=True,
            )  # condense query
        else:
            llm = ChatOpenAI(
                model=MODEL_NAME,
                temperature=temperature,
                request_timeout=LLM_REQUEST_TIMEOUT,
                streaming=True,
                callbacks=[CallbackHandlerDDG()],
            )  # main llm
            llm_condense = ChatOpenAI(
                model=MODEL_NAME,
                temperature=0,  # 0 to have reliable rephrasing
                request_timeout=LLM_REQUEST_TIMEOUT,
                streaming=True,
            )  # condense query

        # Initialize chain for answering queries based on provided doc snippets
        load_chain = load_qa_with_sources_chain if use_sources else load_qa_chain
        combine_docs_chain = (
            load_chain(llm, prompt=prompt_qa, verbose=VERBOSE)
            if prompt_qa
            else load_chain(llm, verbose=VERBOSE)  # use default Langchain prompt
        )

        # Initialize retriever from the provided vectorstore
        if isinstance(vectorstore, ChromaDDG):
            retriever = ChromaDDGRetriever(
                vectorstore=vectorstore, search_type="similarity_ddg"
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
                llm=llm_condense, prompt=CONDENSE_QUESTION_PROMPT, verbose=VERBOSE
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

# Check that the necessary environment variables are set
IS_AZURE = bool(os.getenv("OPENAI_API_BASE"))
EMBEDDINGS_DEPLOYMENT_NAME = os.getenv("EMBEDDINGS_DEPLOYMENT_NAME")
CHAT_DEPLOYMENT_NAME = os.getenv("CHAT_DEPLOYMENT_NAME")

VECTORDB_DIR = os.getenv("VECTORDB_DIR")

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.1))
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 9))

if not os.getenv("OPENAI_API_KEY"):
    print("Please set the environment variables in .env, as shown in .env.example.")
    sys.exit()

# Verify the validity of the db path
if not VECTORDB_DIR or not os.path.exists(VECTORDB_DIR):
    print(
        "You have not specified a valid directory for the vector database. "
        'If you have not created one yet, please do so by running "python ingest_confluence.py", '
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
    TWO_BOTS = os.getenv("TWO_BOTS", False)

    bot = create_bot(vectorstore)
    if TWO_BOTS:
        bot2 = create_bot(vectorstore)  # can put some other params here

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

        # Parse the query to extract search params, if any
        query, search_params = parse_query(query)

        # Get response from bot
        result = bot(
            {
                "question": query,
                "chat_history": chat_history,
                "search_params": search_params,
                # "search_params": {"where_document": {"$contains": "some text"}},
            }
        )
        reply = result["answer"]

        # Print reply
        # print(f"AI: {reply}") - no need, it's streamed to stdout now
        print()
        print(DELIMITER)

        if TWO_BOTS:
            result2 = bot2({"question": query, "chat_history": chat_history})
            reply2 = result2["answer"]
            print()
            print(f"AI2: {reply2}")
            print(DELIMITER)

        # Update chat history
        chat_history.append((query, reply))

        print(f"Standalone query: {result['generated_question']}")
        print(DELIMITER)

        # Get sources
        source_links = get_source_links(result)
        print("Sources:")
        print(*source_links, sep="\n")
        print(DELIMITER)
