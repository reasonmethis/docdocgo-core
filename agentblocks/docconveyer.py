import uuid
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from utils.lang_utils import ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN, get_num_tokens

# class DocData(BaseModel):
#     text: str | None = None
#     source: str | None = None
#     num_tokens: int | None = None
#     doc_uuid: str | None = None
# error: str | None = None
# is_ingested: bool = False

def _split_doc_based_on_tokens(doc: Document, max_tokens: int, target_num_chars: int) -> list[Document]:
    """
    Helper function for the main function below that definitely splits the provided document.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_num_chars,
        chunk_overlap=0,
        add_start_index=True,  # metadata will include start_index of snippet in original doc
    )
    candidate_new_docs = text_splitter.create_documents([doc])
    new_docs = []

    # Calculate the number of tokens in each part and split further if needed
    for maybe_new_doc in candidate_new_docs:
        maybe_new_doc.metadata["num_tokens"] = get_num_tokens(
            maybe_new_doc.page_content
        )

        # If the part is sufficiently small, add it to the list of new docs
        if maybe_new_doc.metadata["num_tokens"] <= max_tokens:
            new_docs.append(maybe_new_doc)
            continue

        # If actual num tokens is X times the target, reduce target_num_chars by ~X
        new_target_num_chars = min(
            int(
                target_num_chars
                * max_tokens
                / maybe_new_doc.metadata["num_tokens"]
            ),
            target_num_chars // 2,
        )

        # Split the part further and adjust the start index of each snippet
        new_parts = _split_doc_based_on_tokens(
            maybe_new_doc, max_tokens, new_target_num_chars
        )
        for new_part in new_parts:
            new_part.metadata["start_index"] += maybe_new_doc.metadata["start_index"]

        # Add the new parts to the list of new docs
        new_docs.extend(new_parts)

    return new_docs


def split_doc_based_on_tokens(doc: Document, max_tokens: int) -> list[Document]:
    """
    Split a document into parts based on the number of tokens in each part. Specifically,
    if the number of tokens in a part (or the original doc) is within max_tokens, then the part is
    added to the list of new docs. Otherwise, the part is split further. The resulting Document
    objects are returned as a list and contain the copy of the metadata from the parent doc, plus
    the "start_index" of its occurrence in the parent doc. The metadata will also include the
    "num_tokens" of the part.
    """
    # If the doc is too large then don't count tokens, just split it.
    num_chars = len(doc.page_content)
    if num_chars / ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN > max_tokens :
        # Doc almost certainly has more tokens than max_tokens
        target_num_chars = int(max_tokens * ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN / 2)
    else:
        # Count the tokens to see if we need to split
        if (num_tokens := get_num_tokens(doc.page_content)) <= max_tokens:
            doc.metadata["num_tokens"] = num_tokens
            return [doc]
        # Guess the target number of characters for the text splitter
        target_num_chars = int(num_chars / (num_tokens / max_tokens) / 2)

    return _split_doc_based_on_tokens(doc, max_tokens, target_num_chars)


def split_big_docs(
    docs: list[Document],
    max_tokens: int, # = int(CONTEXT_LENGTH * 0.25),
) -> list[Document]:
    """
    Split each big document into parts, leaving the small ones as they are. Big vs small is
    determined by the number of tokens in the document.
    """
    new_docs = []
    for doc in docs:
        doc_parts = split_doc_based_on_tokens(doc, max_tokens)
        if len(doc_parts) > 1:
            # Create an id representing the original doc
            full_doc_ref = uuid.uuid4().hex[:8]
            for i, doc_part in enumerate(doc_parts):
                doc_part.metadata["part_id"] = f"{full_doc_ref}-{i}"
        
        new_docs.extend(doc_parts)
    return new_docs


def limit_num_docs_by_tokens(docs: list[Document], max_tokens: int):
    """
    Limit the number of documents in a list based on the total number of tokens in the 
    documents. The function returns the number of documents that can be included in the
    list without exceeding the maximum number of tokens, and the total number of tokens
    in the included documents.

    Additionally, the function updates the metadata of each document with the number of
    tokens in the document, if it is not already present.
    """
    tot_tokens = 0
    for i, doc in enumerate(docs):
        if (num_tokens := doc.metadata.get("num_tokens")) is None:
            doc.metadata["num_tokens"] = num_tokens = get_num_tokens(doc.page_content)
        if tot_tokens + num_tokens > max_tokens:
            return i, tot_tokens
        tot_tokens += num_tokens

    return len(docs), tot_tokens