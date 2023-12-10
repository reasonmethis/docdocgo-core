from typing import Any

from langchain.callbacks.base import BaseCallbackHandler
from langchain.chat_models import AzureChatOpenAI, ChatOpenAI
from langchain.prompts.prompt import PromptTemplate

# from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.schema import StrOutputParser

from utils.helpers import MAIN_BOT_PREFIX
from utils.prepare import (
    CHAT_DEPLOYMENT_NAME,
    IS_AZURE,
    LLM_REQUEST_TIMEOUT,
    MODEL_NAME,
    TEMPERATURE,
)
from utils.type_utils import Callbacks


class CallbackHandlerDDG(BaseCallbackHandler):
    def __init__(self, init_str: str = MAIN_BOT_PREFIX):
        self.init_str = init_str

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        print(self.init_str, end="", flush=True)

    def on_llm_new_token(self, token, **kwargs) -> None:
        print(token, end="", flush=True)

    def on_llm_end(self, *args, **kwargs) -> None:
        print()

    def on_retry(self, *args, **kwargs) -> None:
        print(f"ON_RETRY: \nargs = {args}\nkwargs = {kwargs}")


def get_llm_with_callbacks(temperature=None, callbacks: Callbacks = None):
    """Returns a chat model instance (either AzureChatOpenAI or ChatOpenAI, depending
    on the value of IS_AZURE)"""
    if temperature is None:
        temperature = TEMPERATURE
    if IS_AZURE:
        llm = AzureChatOpenAI(
            deployment_name=CHAT_DEPLOYMENT_NAME,
            temperature=temperature,
            request_timeout=LLM_REQUEST_TIMEOUT,
            streaming=True,  # seems to help with timeouts
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


def get_llm(
    temperature=None,
    callbacks: Callbacks = None,
    stream=False,
    init_str=MAIN_BOT_PREFIX,
):
    """
    Return a chat model instance (either AzureChatOpenAI or ChatOpenAI, depending
    on the value of IS_AZURE). If callbacks is passed, it will be used as the
    callbacks for the chat model. Otherwise, if stream is True, then a CallbackHandlerDDG
    will be used with the passed init_str as the init_str.
    """
    if callbacks is None:
        callbacks = [CallbackHandlerDDG(init_str)] if stream else []
    return get_llm_with_callbacks(temperature, callbacks)


def get_llm_with_str_output_parser(**kwargs):
    return get_llm(**kwargs) | StrOutputParser()


def get_prompt_llm_chain(prompt: PromptTemplate, **kwargs):
    return prompt | get_llm(**kwargs) | StrOutputParser()


if __name__ == "__main__":
    # NOTE: Run this file as "python -m components.llm"
    x = CallbackHandlerDDG("BOT: ")
