import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel

from utils.helpers import DEFAULT_CHAT_MODE, command_ids
from utils.type_utils import ChatMode, Props

DBCommand = Enum("DBCommand", "LIST USE RENAME DELETE EXIT NONE")
db_command_to_enum = {
    "list": DBCommand.LIST,
    "use": DBCommand.USE,
    "rename": DBCommand.RENAME,
    "delete": DBCommand.DELETE,
}


class ResearchParams(BaseModel):
    num_iterations_left: int = 1


class ParsedQuery(BaseModel):
    chat_mode: ChatMode = ChatMode.NONE_COMMAND_ID
    message: str = ""
    search_params: Props | None = None
    research_params: ResearchParams | None = None
    db_command: DBCommand | None = None


def get_command(
    text: str, command_dict: dict[str, Any], default_command=None
) -> tuple[Any, str]:
    """
    Extracts a command from the given text and finds its corresponding value in a dictionary,
    returning the value and the remaining text.

    The function splits the text into two parts (command and the remaining text). It then
    looks up the command in the provided command dictionary. If the command isn't found,
    it returns the default command (if provided, otherwise None) and the original text.
    If the command is found but there is no additional text, an empty string is returned
    as the second part of the tuple.
    """
    # Split the text into command and the remaining part (if any)
    split_text = text.split(maxsplit=1)

    # Attempt to find the command in the command dictionary
    try:
        command = command_dict[split_text[0]]
    except (KeyError, IndexError):
        # Return default command and original text if command not found or text is empty
        return default_command, text

    # Return the command and the remaining text (if any)
    try:
        return command, split_text[1]
    except IndexError:
        # If there's no remaining text, return the command and an empty string
        return command, ""


def extract_chat_mode(
    query: str, default: ChatMode = DEFAULT_CHAT_MODE
) -> tuple[ChatMode, str]:
    """Extract the command ID from the query, if any"""
    query = query.strip()
    if query == "help":
        query = "/help"
    return get_command(query, command_ids, default)


def extract_search_params(query: str, mode="normal") -> tuple[str, Props]:
    """
    Extract search params, if any, from the query.

    Args:
        query (str): The query to parse.
        mode (str): The mode to use for parsing. Can be "normal" or "strict".
            In either mode, if the query ends with a JSON object, it is treated
            as search params and removed from the query. In "normal" mode, if it
            does not end with a JSON object but contains substrings in quotes,
            those substrings are treated as search params (but NOT removed from
            the query), namely as substrings that retrieved documents must contain.
    """

    if query.endswith("}"):
        # Find the corresponding opening brace
        brace_count = 0
        for i, char in enumerate(reversed(query)):
            if char == "}":
                brace_count += 1
            elif char == "{":
                brace_count -= 1
            if brace_count == 0:
                # Extract the JSON string at the end and set it as search params
                try:
                    search_params = json.loads(query[-i - 1 :])
                    query = query[: -i - 1]
                    return query, search_params
                except json.decoder.JSONDecodeError:
                    break

    # If we're here, the query does not end with a valid JSON object
    if mode != "normal":
        return query, {}

    # We are in "normal" mode with no JSON object at the end
    # Find all substrings in quotes and treat them as must-have substrings
    substrings_in_quotes = re.findall(r'"([^"]*)"', query)
    # substrings_in_quotes = re.findall(r'"(.*?)"', query) # another way (no '\n')

    # Remove empty strings and duplicates, form a list of $contains filters
    filters = [{"$contains": substr} for substr in set(substrings_in_quotes) if substr]

    # Combine the filters into a single $and filter and return results
    if not filters:
        return query, {}

    if len(filters) == 1:
        return query, {"where_document": filters[0]}

    return query, {"where_document": {"$and": filters}}


def parse_query(query: str, predetermined_chat_mode: ChatMode | None = None) -> ParsedQuery:
    if predetermined_chat_mode:
        chat_mode = predetermined_chat_mode
    else:
        chat_mode, query = extract_chat_mode(query)

    if chat_mode in {
        ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
        ChatMode.DETAILS_COMMAND_ID,
        ChatMode.QUOTES_COMMAND_ID,
    }:
        x, y = extract_search_params(query)
        return ParsedQuery(chat_mode=chat_mode, message=x, search_params=y)

    if chat_mode == ChatMode.DB_COMMAND_ID:
        x, y = get_command(query, db_command_to_enum, DBCommand.NONE)
        return ParsedQuery(chat_mode=chat_mode, db_command=x, message=y)

    return ParsedQuery(chat_mode=chat_mode, message=query)
