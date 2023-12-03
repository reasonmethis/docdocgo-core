from typing import Any

from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.schema import StrOutputParser
from langchain.prompts.prompt import PromptTemplate
from langchain.chat_models import ChatOpenAI, AzureChatOpenAI
from langchain.callbacks.base import BaseCallbackHandler

from utils.helpers import DEFAULT_STREAM_PREFIX
from utils.prepare import TEMPERATURE, IS_AZURE, CHAT_DEPLOYMENT_NAME
from utils.prepare import MODEL_NAME, LLM_REQUEST_TIMEOUT


def get_llm(temperature=None, stream=False, init_str=DEFAULT_STREAM_PREFIX):
    """Returns a chat model instance (either AzureChatOpenAI or ChatOpenAI, depending
    on the value of IS_AZURE)"""
    if temperature is None:
        temperature = TEMPERATURE
    callbacks = [CallbackHandlerDDG(init_str)] if stream else []
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


def get_llm_with_str_output_parser(**kwargs):
    return get_llm(**kwargs) | StrOutputParser()


def get_prompt_llm_chain(prompt: PromptTemplate, **kwargs):
    return prompt | get_llm(**kwargs) | StrOutputParser()


class CallbackHandlerDDG(BaseCallbackHandler):
    def __init__(self, init_str: str = DEFAULT_STREAM_PREFIX):
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


if __name__ == "__main__":
    # NOTE: Run this file as "python -m components.llm"
    x = CallbackHandlerDDG("BOT: ")
