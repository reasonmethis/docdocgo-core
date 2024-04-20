from agentblocks.websearch import (
    get_web_search_result_links_from_prompt,
)
from utils.chat_state import ChatState
from utils.type_utils import Props

HEATSEEK_PROMPT = ""


# NOTE: should catch and handle exceptions in main handler
def get_research_heatseek_response(chat_state: ChatState) -> Props:
    message = chat_state.message

    links = get_web_search_result_links_from_prompt(
        HEATSEEK_PROMPT,
        inputs={"message": message},
        num_links=100,
        chat_state=chat_state,
    )
