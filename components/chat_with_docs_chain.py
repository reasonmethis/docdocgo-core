"""Chain for chatting with a vector database."""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Callable

from pydantic import Extra

from langchain.callbacks.manager import (
    AsyncCallbackManagerForChainRun,
    CallbackManagerForChainRun,
)
from langchain.chains.base import Chain
from langchain.chains.combine_documents.base import BaseCombineDocumentsChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.chains.llm import LLMChain
from langchain.schema import BaseRetriever, Document
from langchain.schema.messages import BaseMessage

from utils.type_utils import JSONish, PairwiseChatHistory
from utils.helpers import DELIMITER
from utils import lang_utils


class ChatWithDocsChain(Chain):
    """
    Chain for chatting with documents using a retriever. This class incorporates
    both the chat history and the retrieved documents into the final prompt and
    limits the number of tokens in both to stay within the specified limits. It
    dynamically adjusts the number of documents to keep based on their relevance
    scores, and then correspondingly adjusts the number of chat history messages
    (shortening the first message pair if necessary). 

    Attributes:
        combine_docs_chain (BaseCombineDocumentsChain): The chain used to
            combine any retrieved documents.
        question_generator (LLMChain): The chain used to generate a new question
            for the sake of retrieval. This chain will take in the current question
            (with variable `question`) and any chat history (with variable
            `chat_history`) and will produce a new standalone question to be used
            later on.
        retriever (BaseRetriever): Retriever to use to fetch documents.
        max_tokens_limit_rephrase (int): Chat history token limit for submitting
            to the standalone query generator.
        max_tokens_limit_qa (int): Combined docs + chat history token limit for
            submitting to the chat/qa chain.
        max_tokens_limit_chat (int): Chat history token limit for submitting to
            the chat/qa chain. (NOTE: if there are few docs, this
            limit may be exceeded.)
        output_key (str): The output key to return the final answer of this chain
            in. Default is 'answer'.
        return_source_documents (bool): Indicates whether to return the retrieved
            source documents as part of the final result. Default is False.
        return_generated_question (bool): Indicates whether to return the generated
            question as part of the final result. Default is False.
        get_chat_history (Callable[[PairwiseChatHistory], str] | None): An optional
            function to get a string of the chat history. Default is None.
    """

    combine_docs_chain: BaseCombineDocumentsChain
    question_generator: LLMChain
    retriever: BaseRetriever

    max_tokens_limit_rephrase: int = 2000
    max_tokens_limit_qa: int = 3000  # docs + chat (no prompt); must leave room for ans
    max_tokens_limit_chat: int = 1000
    output_key: str = "answer"
    return_source_documents: bool = False
    return_generated_question: bool = False
    get_chat_history: Callable[[PairwiseChatHistory], str] | None = None

    class Config:
        """Configuration for this pydantic object."""

        extra = Extra.forbid
        arbitrary_types_allowed = True
        allow_population_by_field_name = True

    @property
    def input_keys(self) -> list[str]:
        """Input keys."""
        return ["question", "chat_history"]

    @property
    def output_keys(self) -> list[str]:
        """Return the output keys.

        :meta private:
        """
        res = [self.output_key]
        if self.return_source_documents:
            res.append("source_documents")
        if self.return_generated_question:
            res.append("generated_question")
        return res

    def _limit_token_count_in_docs(
        self, docs: list[Document], max_tokens: int
    ) -> tuple[list[Document], int]:
        """Reduce the number of tokens in the documents below the limit."""

        if not isinstance(self.combine_docs_chain, StuffDocumentsChain):
            raise NotImplementedError("Not implemented for non-stuff chains.")

        # Get the number of tokens in each document
        token_counts = [
            self.combine_docs_chain.llm_chain.llm.get_num_tokens(doc.page_content)
            for doc in docs
        ]

        # Reduce the number of documents until we're below the limit
        token_count = sum(token_counts)
        num_docs = len(docs)
        while token_count > max_tokens and num_docs:
            num_docs -= 1
            token_count -= token_counts[num_docs]

        return docs[:num_docs], token_count

    def _call(
        self,
        inputs: JSONish,
        run_manager: CallbackManagerForChainRun | None = None,
    ) -> JSONish:
        """Run the chain."""

        _run_manager = run_manager or CallbackManagerForChainRun.get_noop_manager()
        _get_chat_history_str = (
            self.get_chat_history or lang_utils.pairwise_chat_history_to_buffer_string
        )
        # _get_chat_history_str = self.get_chat_history or _get_chat_history

        # Get user's query and chat history from inputs
        user_query = inputs["question"]
        chat_history = inputs["chat_history"]
        search_kwargs = inputs.get("search_params", {})  # e.g. {"filter": {...}}

        # Convert chat history to unified format (PairwiseChatHistory)
        # (it could instead be a list of messages, in which case we convert it)
        if (
            chat_history
            and isinstance(chat_history, list)
            and isinstance(chat_history[0], BaseMessage)
        ):
            chat_history = lang_utils.msg_list_chat_history_to_pairwise(chat_history)

        # Initially limit chat history and calculate token counts in each msg pair
        chat_history_token_limit = max(
            self.max_tokens_limit_rephrase, self.max_tokens_limit_qa
        )
        if isinstance(self.combine_docs_chain, StuffDocumentsChain):
            llm_for_token_counting = self.combine_docs_chain.llm_chain.llm
        else:
            # Above LLM does not exist so use the question generator's LLM
            llm_for_token_counting = self.question_generator.llm

        chat_history, chat_history_token_counts = lang_utils.limit_chat_history(
            chat_history,
            max_token_limit=chat_history_token_limit,
            llm_for_token_counting=llm_for_token_counting,
        )

        # Generate a standalone query using chat history
        if not chat_history:
            standalone_query = user_query  # no chat history to rephrase
        else:
            chat_history_for_rephrasing, _ = lang_utils.limit_chat_history(
                chat_history,
                max_token_limit=self.max_tokens_limit_rephrase,
                cached_token_counts=chat_history_token_counts,
                llm_for_token_counting=llm_for_token_counting,
            )

            standalone_query = self.question_generator.run(
                question=user_query,
                chat_history=_get_chat_history_str(chat_history_for_rephrasing),
                callbacks=_run_manager.get_child(),
            )

        # Get relevant documents using the standalone query
        docs = self.retriever.get_relevant_documents(
            standalone_query,
            callbacks=_run_manager.get_child(),
            **search_kwargs,
        )

        # Find limited token number for chat history
        # token_count_chat = 0
        # for token_count in reversed(chat_history_token_counts):
        #     token_count_chat += token_count
        #     if token_count_chat > self.max_tokens_limit_chat:
        #         token_count_chat -= token_count  # undo
        #         break
        _, new_chat_hist_token_counts = lang_utils.limit_chat_history(
            chat_history,
            max_token_limit=self.max_tokens_limit_chat,
            llm_for_token_counting=llm_for_token_counting,
            cached_token_counts=chat_history_token_counts,
        )
        # NOTE The only difference between new and old token counts (apart from length)
        # is that the very first message pair may have been shortened.
        token_count_chat = sum(new_chat_hist_token_counts)

        # Reduce number of docs to fit in overall token limit
        max_tokens_limit_docs = self.max_tokens_limit_qa - token_count_chat
        docs, token_count_docs = self._limit_token_count_in_docs(
            docs, max_tokens_limit_docs
        )

        # Reevaluate limit for chat history (maybe can fit more) and limit it
        chat_history_for_qa, _ = lang_utils.limit_chat_history(
            chat_history,
            max_token_limit=self.max_tokens_limit_qa - token_count_docs,
            llm_for_token_counting=llm_for_token_counting,
            cached_token_counts=chat_history_token_counts,
        )

        # Submit limited docs and chat history to the chat/qa chain
        new_inputs = inputs.copy()
        new_inputs["chat_history"] = _get_chat_history_str(chat_history_for_qa)

        answer = self.combine_docs_chain.run(
            input_documents=docs, callbacks=_run_manager.get_child(), **new_inputs
        )

        # Format and return the answer
        output = {self.output_key: answer}
        if self.return_source_documents:
            output["source_documents"] = docs
        if self.return_generated_question:
            output["generated_question"] = standalone_query
        return output

    async def _acall(
        self,
        inputs: dict[str, Any],
        run_manager: AsyncCallbackManagerForChainRun | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("Async version (_acall) not implemented yet.")
        _run_manager = run_manager or AsyncCallbackManagerForChainRun.get_noop_manager()
        question = inputs["question"]
        get_chat_history = self.get_chat_history or _get_chat_history
        chat_history_str = get_chat_history(inputs["chat_history"])
        if chat_history_str:
            callbacks = _run_manager.get_child()
            new_question = await self.question_generator.arun(
                question=question, chat_history=chat_history_str, callbacks=callbacks
            )
        else:
            new_question = question
        accepts_run_manager = (
            "run_manager" in inspect.signature(self._aget_docs).parameters
        )
        if accepts_run_manager:
            docs = await self._aget_docs(new_question, inputs, run_manager=_run_manager)
        else:
            docs = await self._aget_docs(new_question, inputs)  # type: ignore[call-arg]

        new_inputs = inputs.copy()
        if self.rephrase_question:
            new_inputs["question"] = new_question
        new_inputs["chat_history"] = chat_history_str
        answer = await self.combine_docs_chain.arun(
            input_documents=docs, callbacks=_run_manager.get_child(), **new_inputs
        )
        output: dict[str, Any] = {self.output_key: answer}
        if self.return_source_documents:
            output["source_documents"] = docs
        if self.return_generated_question:
            output["generated_question"] = new_question
        return output

    def save(self, file_path: Path | str) -> None:
        if self.get_chat_history:
            raise ValueError("Chain not saveable when `get_chat_history` is not None.")
        super().save(file_path)
