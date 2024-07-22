import uuid

# class DocData(BaseModel):
#     text: str | None = None
#     source: str | None = None
#     num_tokens: int | None = None
#     doc_uuid: str | None = None
# error: str | None = None
# is_ingested: bool = False
from typing import TypeVar
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from utils.lang_utils import ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN, get_num_tokens
from utils.prepare import get_logger
from utils.type_utils import Doc
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = get_logger()

DocT = TypeVar("DocT", Document, Doc)


def _split_doc_based_on_tokens(
    doc: Document | Doc, max_tokens: float, target_num_chars: int
) -> list[Document]:
    """
    Helper function for the main function below that definitely splits the provided document.
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=target_num_chars,
        chunk_overlap=0,
        add_start_index=True,  # metadata will include start_index of snippet in original doc
    )
    candidate_new_docs = text_splitter.create_documents(
        texts=[doc.page_content], metadatas=[doc.metadata]
    )
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
            int(target_num_chars * max_tokens / maybe_new_doc.metadata["num_tokens"]),
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


def split_doc_based_on_tokens(doc: DocT, max_tokens: float) -> list[DocT]:
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
    if num_chars / ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN > max_tokens:
        # Doc almost certainly has more tokens than max_tokens
        target_num_chars = int(max_tokens * ROUGH_UPPER_LIMIT_AVG_CHARS_PER_TOKEN / 2)
    else:
        # Count the tokens to see if we need to split
        if (num_tokens := get_num_tokens(doc.page_content)) <= max_tokens:
            doc.metadata["num_tokens"] = num_tokens
            return [doc]
        # Guess the target number of characters for the text splitter
        target_num_chars = int(num_chars / (num_tokens / max_tokens) / 2)

    documents = _split_doc_based_on_tokens(doc, max_tokens, target_num_chars)
    if isinstance(doc, Document):
        return documents
    else:
        return [Doc.from_lc_doc(d) for d in documents]


def break_up_big_docs(
    docs: list[DocT],
    max_tokens: float,  # = int(CONTEXT_LENGTH * 0.25),
) -> list[DocT]:
    """
    Split each big document into parts, leaving the small ones as they are. Big vs small is
    determined by how the number of tokens in the document compares to the max_tokens parameter.
    """
    logger.info(f"Breaking up {len(docs)} docs into parts with max_tokens={max_tokens}")
    new_docs = []
    for doc in docs:
        doc_parts = split_doc_based_on_tokens(doc, max_tokens)
        logger.debug(f"Split doc {doc.metadata.get('source')} into {len(doc_parts)} parts")
        if len(doc_parts) > 1:
            # Create an id representing the original doc
            full_doc_ref = uuid.uuid4().hex[:8]
            for i, doc_part in enumerate(doc_parts):
                doc_part.metadata["full_doc_ref"] = full_doc_ref
                doc_part.metadata["part_id"] = str(i)

        new_docs.extend(doc_parts)
    return new_docs


def limit_num_docs_by_tokens(
    docs: list[Document | Doc], max_tokens: float
) -> tuple[int, int]:
    """
    Limit the number of documents in a list based on the total number of tokens in the
    documents.

    Return the number of documents that can be included in the
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


class DocConveyer(BaseModel):
    docs: list[Doc] = Field(default_factory=list)
    max_tokens_for_breaking_up_docs: int | float | None = None
    idx_first_not_done: int = 0  # done = "pushed out" by get_next_docs

    def __init__(self, **data):
        super().__init__(**data)
        if self.max_tokens_for_breaking_up_docs is not None:
            self.docs = break_up_big_docs(
                self.docs, self.max_tokens_for_breaking_up_docs
            )

    @property
    def num_available_docs(self):
        return len(self.docs) - self.idx_first_not_done
    
    def add_docs(self, docs: list[Doc]):
        if self.max_tokens_for_breaking_up_docs is not None:
            docs = break_up_big_docs(docs, self.max_tokens_for_breaking_up_docs)
        self.docs.extend(docs)

    def get_next_docs(
        self,
        max_tokens: float,
        max_docs: int | None = None,
        max_full_docs: int | None = None,
    ) -> list[Doc]:
        logger.debug(f"{self.num_available_docs} docs available")
        num_docs, _ = limit_num_docs_by_tokens(
            self.docs[self.idx_first_not_done :], max_tokens
        )
        if max_docs is not None:
            num_docs = min(num_docs, max_docs)

        if max_full_docs is not None:
            num_full_docs = 0
            old_full_doc_ref = None
            new_num_docs = 0
            for doc in self.docs[
                self.idx_first_not_done : self.idx_first_not_done + num_docs
            ]:
                if num_full_docs >= max_full_docs:
                    break
                new_num_docs += 1
                new_full_doc_ref = doc.metadata.get("full_doc_ref")
                if new_full_doc_ref is None or new_full_doc_ref != old_full_doc_ref:
                    num_full_docs += 1
                    old_full_doc_ref = new_full_doc_ref
            num_docs = new_num_docs

        self.idx_first_not_done += num_docs
        logger.debug(f"Returning {num_docs} docs")
        return self.docs[self.idx_first_not_done - num_docs : self.idx_first_not_done]

    def clear_done_docs(self):
        self.docs = self.docs[self.idx_first_not_done :]
        self.idx_first_not_done = 0
