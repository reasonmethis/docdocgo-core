from agentblocks.websearch import (
    get_web_search_result_links_from_prompt,
)
from utils.chat_state import ChatState
from utils.helpers import format_nonstreaming_answer
from utils.type_utils import JSONishDict, Props

HEATSEEK_PROMPT = ""

def get_new_heatseek_response(chat_state: ChatState) -> Props:
    message = chat_state.message
    num_iterations = chat_state.parsed_query.research_params.num_iterations_left

    # Get links from prompt
    links = get_web_search_result_links_from_prompt(
        HEATSEEK_PROMPT,
        inputs={"message": message},
        num_links=100,
        chat_state=chat_state,
    )

def get_heatseek_in_progress_response(chat_state: ChatState, hs_data: JSONishDict) -> Props:
    message = chat_state.message
    num_iterations = chat_state.parsed_query.research_params.num_iterations_left
    return format_nonstreaming_answer(
        f"NOT YET IMPLEMENTED: Your heatseek is in progress. {num_iterations} iterations left."
    )

# NOTE: should catch and handle exceptions in main handler
def get_research_heatseek_response(chat_state: ChatState) -> Props:
    if chat_state.message:
        return get_new_heatseek_response(chat_state)

    hs_data = chat_state.agent_data.get("hs_data")
    if hs_data:
        return get_heatseek_in_progress_response(chat_state, hs_data)
    
    return format_nonstreaming_answer("To start a new heatseek, type `/re heatseek <your query>`.")
