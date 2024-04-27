import uuid

from langchain_core.documents import Document

from agents.dbmanager import construct_full_collection_name
from components.chroma_ddg import ChromaDDG, exists_collection
from utils.chat_state import ChatState
from utils.docgrab import load_into_chroma
from utils.prepare import get_logger

logger = get_logger()

SMALL_WORDS = {"a", "an", "the", "of", "in", "on", "at", "for", "to", "and", "or"}
SMALL_WORDS |= {"is", "are", "was", "were", "be", "been", "being", "am", "what"}
SMALL_WORDS |= {"what", "which", "who", "whom", "whose", "where", "when", "how"}
SMALL_WORDS |= {"this", "that", "these", "those", "there", "here", "can", "could"}
SMALL_WORDS |= {"i", "you", "he", "she", "it", "we", "they", "me", "him", "her"}
SMALL_WORDS |= {"my", "your", "his", "her", "its", "our", "their", "mine", "yours"}
SMALL_WORDS |= {"some", "any"}


def get_collection_name_from_query(query: str, chat_state: ChatState) -> str:
    # Decide on the collection name consistent with ChromaDB's naming rules
    query_words = [x.lower() for x in query.split()]
    words = []
    words_excluding_small = []
    for word in query_words:
        word_just_alnum = "".join(x for x in word if x.isalnum())
        if not word_just_alnum:
            break
        words.append(word_just_alnum)
        if word not in SMALL_WORDS:
            words_excluding_small.append(word_just_alnum)

    words = words_excluding_small if len(words_excluding_small) > 2 else words

    new_coll_name = "-".join(words[:3])[:35].rstrip("-")

    # Screen for too short collection names or those that are convetible to a number
    try:
        if len(new_coll_name) < 3 or int(new_coll_name) is not None:
            new_coll_name = f"collection-{new_coll_name}".rstrip("-")
    except ValueError:
        pass

    # Construct full collection name (preliminary)
    new_coll_name = construct_full_collection_name(chat_state.user_id, new_coll_name)

    new_coll_name_final = new_coll_name

    # Check if collection exists, if so, add a number to the end
    for i in range(2, 1000000):
        if not exists_collection(new_coll_name_final, chat_state.vectorstore.client):
            return new_coll_name_final
        new_coll_name_final = f"{new_coll_name}-{i}"


def start_new_collection(
    *,
    likely_coll_name: str,
    docs: list[Document],
    collection_metadata: dict[str, str],
    chat_state: ChatState,
) -> ChromaDDG:
    """
    Create a new collection and load provided documents and metadata into it.

    Does not check if the collection already exists. It's ok to pass an empty list of documents.
    If the collection name is invalid, it will replace it with a random valid one.
    """
    logger.info("Creating new collection and loading data")

    for i in range(2):
        try:
            vectorstore = load_into_chroma(
                docs,
                collection_name=likely_coll_name,
                openai_api_key=chat_state.openai_api_key,
                chroma_client=chat_state.vectorstore.client,
                collection_metadata=collection_metadata,
            )
            break  # success
        except Exception as e:  # bad name error may not be ValueError in docker mode
            logger.error(f"Error ingesting documents into ChromaDB: {e}")
            if i != 0 or "Expected collection name" not in str(e):
                raise e  # i == 1 means tried normal name and random name, give up

            # Create a random valid collection name and try again
            likely_coll_name = construct_full_collection_name(
                chat_state.user_id, "collection-" + uuid.uuid4().hex[:8]
            )

    logger.info(f"Finished loading data into new collection {likely_coll_name}")
    return vectorstore
