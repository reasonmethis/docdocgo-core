from typing import Any

from langchain.schema.output_parser import StrOutputParser
from langchain.chat_models import ChatOpenAI, AzureChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler

from utils.prepare import TEMPERATURE, IS_AZURE, CHAT_DEPLOYMENT_NAME
from utils.prepare import MODEL_NAME, LLM_REQUEST_TIMEOUT


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


def get_llm_with_output_parser(temperature=None, print_streamed=False):
    return (
        get_llm(temperature=temperature, print_streamed=print_streamed)
        | StrOutputParser()
    )


class CallbackHandlerDDG(BaseCallbackHandler):
    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], **kwargs: Any
    ) -> None:
        print("BOT: ", end="", flush=True)

    def on_llm_new_token(self, token, **kwargs) -> None:
        print(token, end="", flush=True)

    def on_retry(self, *args, **kwargs):
        print(f"ON_RETRY: \nargs = {args}\nkwargs = {kwargs}")
