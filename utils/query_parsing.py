import ast
import json
import re
from enum import Enum
from typing import Any, Callable, Container

from pydantic import BaseModel

from utils.helpers import DEFAULT_CHAT_MODE, command_ids
from utils.prepare import get_logger
from utils.type_utils import AccessCodeType, ChatMode, Props

logger = get_logger()

DBCommand = Enum("DBCommand", "LIST USE RENAME DELETE STATUS EXIT NONE")
db_command_to_enum = {
    "list": DBCommand.LIST,
    "use": DBCommand.USE,
    "rename": DBCommand.RENAME,
    "delete": DBCommand.DELETE,
    "status": DBCommand.STATUS,
}

ResearchCommand = Enum(
    "ResearchCommand",
    "NEW MORE COMBINE AUTO DEEPER ITERATE VIEW SET_QUERY SET_SEARCH_QUERIES "
    "SET_REPORT_TYPE CLEAR STARTOVER AUTO_UPDATE_SEARCH_QUERIES HEATSEEK NONE",
)
research_command_to_enum = {
    "iterate": ResearchCommand.ITERATE,
    "new": ResearchCommand.NEW,
    "more": ResearchCommand.MORE,
    "combine": ResearchCommand.COMBINE,
    "auto": ResearchCommand.AUTO,
    "deeper": ResearchCommand.DEEPER,
    "view": ResearchCommand.VIEW,
    "set-query": ResearchCommand.SET_QUERY,
    "sq": ResearchCommand.SET_QUERY,  # "sq" is a shorthand for "set-query
    "set-report-type": ResearchCommand.SET_REPORT_TYPE,
    "srt": ResearchCommand.SET_REPORT_TYPE,  # "srt" is a shorthand for "set-report-type
    "set-search-queries": ResearchCommand.SET_SEARCH_QUERIES,
    "ssq": ResearchCommand.SET_SEARCH_QUERIES,  # "ssq" is a shorthand for "set-search-queries
    "clear": ResearchCommand.CLEAR,
    "startover": ResearchCommand.STARTOVER,
    "auto-update-search-queries": ResearchCommand.AUTO_UPDATE_SEARCH_QUERIES,
    "ausq": ResearchCommand.AUTO_UPDATE_SEARCH_QUERIES,
    "heatseek": ResearchCommand.HEATSEEK,
    "hs": ResearchCommand.HEATSEEK,  # "hs" is a shorthand for "heatseek
}
research_view_subcommands = {"main", "base", "combined", "stats"}

IngestCommand = Enum("IngestCommand", "NEW ADD DEFAULT")
ingest_command_to_enum = {
    "new": IngestCommand.NEW,
    "add": IngestCommand.ADD,
}
# DEFAULT means: if collection starts with INGESTED_DOCS_INIT_PREFIX, use ADD, else use NEW

ShareCommand = Enum("ShareCommand", "PUBLIC OWNER EDITOR VIEWER REVOKE NONE")
ShareRevokeSubCommand = Enum(
    "ShareRevokeSubCommand", "CODE USER ALL_CODES ALL_USERS NONE"
)
share_command_to_enum = {
    # "public": ShareCommand.PUBLIC, # not implemented yet
    "editor": ShareCommand.EDITOR,
    "viewer": ShareCommand.VIEWER,
    "owner": ShareCommand.OWNER,
    "revoke": ShareCommand.REVOKE,
    "delete": ShareCommand.REVOKE,
}
share_subcommand_to_code_type = {
    "pwd": AccessCodeType.NEED_ALWAYS,
    # "unlock-code": AccessCodeType.NEED_ONCE,
    # "uc": AccessCodeType.NEED_ONCE,
}
share_revoke_subcommand_to_enum = {
    "code": ShareRevokeSubCommand.CODE,
    "pwd": ShareRevokeSubCommand.CODE,
    "user": ShareRevokeSubCommand.USER,
    "all-codes": ShareRevokeSubCommand.ALL_CODES,
    "all-pwds": ShareRevokeSubCommand.ALL_CODES,
    "all-users": ShareRevokeSubCommand.ALL_USERS,
}
HEATSEEKER_DEFAULT_NUM_ITERATIONS = 1

ExportCommand = Enum("ExportCommand", "CHAT KB NONE")
export_command_to_enum = {
    "chat": ExportCommand.CHAT,
}


class ResearchParams(BaseModel):
    task_type: ResearchCommand
    sub_task: str | None = None
    num_iterations_left: int = 1


class ShareParams(BaseModel):
    share_type: ShareCommand
    access_code_type: AccessCodeType | None = None
    access_code: str | None = None
    revoke_type: ShareRevokeSubCommand | None = None
    code_or_user_to_revoke: str | None = None


class ParsedQuery(BaseModel):
    chat_mode: ChatMode = ChatMode.NONE_COMMAND_ID
    message: str = ""

    # Normally, only one of the following fields should be set
    search_params: Props | None = None
    research_params: ResearchParams | None = None
    db_command: DBCommand | None = None
    ingest_command: IngestCommand | None = None
    export_command: ExportCommand | None = None
    share_params: ShareParams | None = None

    def is_ingestion_needed(self) -> bool:
        if self.research_params and self.research_params.task_type in {
            ResearchCommand.NEW,
            ResearchCommand.AUTO,  # NOTE: doesn't always need ingestion
            ResearchCommand.DEEPER,
            ResearchCommand.ITERATE,
            ResearchCommand.MORE,
        }:
            return True

        if self.chat_mode in {
            ChatMode.SUMMARIZE_COMMAND_ID,
            ChatMode.INGEST_COMMAND_ID,
        }:
            return True

        return False


def get_command(
    text: str, commands: dict[str, Any] | Container[str], default_command=None
) -> tuple[Any, str]:
    """
    Extract a command from the given text and find its corresponding value in a dictionary,
    if provided, returning the value and the remaining text. If instead of a dictionary, a list,
    set, or other container of command strings is provided, return the command string and the
    remaining text.

    The function splits the text into two parts (command and the remaining text). It then
    determines the command value from the provided command dictionary or container. If the
    command isn't found, it returns the default command (or None) and the original text.
    If the command is found but there is no additional text, an empty string is returned
    as the second part of the tuple.
    """
    # Split the text into command and the remaining part (if any)
    split_text = text.split(maxsplit=1)

    # Attempt to find the command in the command dictionary or container
    try:
        if isinstance(commands, dict):
            command = commands[split_text[0]]
        elif (command := split_text[0]) not in commands:
            return default_command, text
    except (KeyError, IndexError):
        # Return default command and original text if command not found or text is empty
        return default_command, text

    # Return the command and the remaining text (if any)
    try:
        return command, split_text[1]
    except IndexError:
        # If there's no remaining text, return the command and an empty string
        return command, ""


def get_value(text: str, transform: Callable) -> tuple[Any, str]:
    """
    Extract the first word from the given text and apply the specified transformation
    function to it, returning the transformed value and the remaining text.

    If transforming fails or the text is empty, the function returns (None, text). If there's no
    remaining text, the second part of the returned tuple is an empty string.
    """
    # Split the text into the first word and the remaining part
    split_text = text.split(maxsplit=1)

    # Attempt to apply the transformation function to the first word
    try:
        value = transform(split_text[0])
    except Exception:
        # Return None and original text if transformation fails or text is empty
        return None, text

    # Return the resulting value and the remaining text (if any)
    try:
        return value, split_text[1]
    except IndexError:
        # If there's no remaining text, return the value and an empty string
        return value, ""


def get_int(
    text: str, min_val: int | None = None, max_val: int | None = None
) -> tuple[int | None, str]:
    val, rest = get_value(text, int)
    if (
        val is None
        or (min_val is not None and val < min_val)
        or (max_val is not None and val > max_val)
    ):
        return None, text
    return val, rest


def get_int_or_command(
    text: str,
    commands: Container[str],
    min_val: int | None = None,
    max_val: int | None = None,
) -> tuple[int | str | None, str]:
    val, rest = get_int(text, min_val, max_val)
    if val is not None:
        return val, rest
    return get_command(text, commands, None)


def extract_chat_mode(
    query: str, default: ChatMode = DEFAULT_CHAT_MODE
) -> tuple[ChatMode, str]:
    """Extract the chat mode from the query and return it along with the remaining text."""
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


def standardize_search_queries(query: str) -> str:
    """
    Extract a list of search queries from the given query.
    Return the resulting list of queries as a JSON string.

    There are two ways to specify search queries:
    1. By providing a list of queries as a Python list in string format.
    2. By providing a list of queries as a comma-separated string.

    If the query can be parsed as a Python list in string format, it is treated as such. If not,
    method 2 is used.
    """
    try:
        # Attempt to parse the query using ast.literal_eval
        search_queries = ast.literal_eval(query)  # to handle single quotes
        if not isinstance(search_queries, list):
            raise SyntaxError
        for q in search_queries:
            if not isinstance(q, str):
                raise SyntaxError
        return json.dumps(search_queries)
    except (ValueError, SyntaxError):
        # Fallback to comma-separated string parsing
        search_queries = [q.strip() for q in query.split(",")]
        return json.dumps(search_queries)


def parse_research_command(orig_query: str) -> tuple[ResearchParams, str]:
    task_type, query = get_command(orig_query, research_command_to_enum)

    # Task types requiring a query but not a number of iterations or sub-task
    if task_type in {
        None,
        ResearchCommand.NEW,
        ResearchCommand.SET_QUERY,
        ResearchCommand.SET_REPORT_TYPE,
        ResearchCommand.SET_SEARCH_QUERIES,
    }:
        if not query:
            task_type = ResearchCommand.NONE  # show help if no query
        elif task_type is None:
            task_type = ResearchCommand.NEW
        elif task_type == ResearchCommand.SET_SEARCH_QUERIES:
            query = standardize_search_queries(query)
        return ResearchParams(task_type=task_type), query

    if task_type == ResearchCommand.VIEW:
        sub_task, query = get_command(query, research_view_subcommands, "main")
        if query:  # view task doesn't take any additional query after sub_task
            return ResearchParams(task_type=ResearchCommand.NEW), orig_query
        return ResearchParams(task_type=task_type, sub_task=sub_task), ""

    # Task types not needing a query or a number of iterations
    if task_type in {
        ResearchCommand.CLEAR,
        ResearchCommand.STARTOVER,
        ResearchCommand.AUTO_UPDATE_SEARCH_QUERIES,
    }:
        if query:  # assume that "task type" is actually part of the query
            return ResearchParams(task_type=ResearchCommand.NEW), orig_query
        return ResearchParams(task_type=task_type), ""

    # We have a task type that supports multiple iterations:
    # MORE, COMBINE, AUTO, ITERATE, DEEPER, HEATSEEK
    num_iterations, query_after_get_int = get_int(query)

    if num_iterations is None:
        num_iterations = (
            HEATSEEKER_DEFAULT_NUM_ITERATIONS
            if task_type == ResearchCommand.HEATSEEK
            else 1
        )

    # Most of these task types require the remaining query to be empty
    if num_iterations > 0 and (
        not query_after_get_int or task_type == ResearchCommand.HEATSEEK
    ):
        return ResearchParams(
            task_type=task_type, num_iterations_left=num_iterations
        ), query_after_get_int

    # We have e.g. "/research auto somequery", treat "auto" as part of the query
    # OR no valid number of iterations specified, treat e.g. -10 as part of actual query
    return ResearchParams(task_type=ResearchCommand.NEW), orig_query


def parse_share_command(orig_query: str) -> ShareParams:
    command, rest = get_command(orig_query, share_command_to_enum, ShareCommand.NONE)
    if command == ShareCommand.NONE:
        return ShareParams(share_type=ShareCommand.NONE)

    if command == ShareCommand.REVOKE:
        subcommand, rest = get_command(
            rest, share_revoke_subcommand_to_enum, ShareRevokeSubCommand.NONE
        )
        if subcommand == ShareRevokeSubCommand.NONE:
            return ShareParams(share_type=ShareCommand.NONE)
        return ShareParams(
            share_type=ShareCommand.REVOKE,
            revoke_type=subcommand,
            code_or_user_to_revoke=rest,
        )

    subcommand, rest = get_command(rest, share_subcommand_to_code_type, None)
    return ShareParams(
        share_type=command, access_code_type=subcommand, access_code=rest
    )


def parse_query(
    query: str, predetermined_chat_mode: ChatMode | None = None
) -> ParsedQuery:
    if predetermined_chat_mode:
        chat_mode = predetermined_chat_mode
    else:
        chat_mode, query = extract_chat_mode(query)

    if chat_mode in {
        ChatMode.CHAT_WITH_DOCS_COMMAND_ID,
        ChatMode.DETAILS_COMMAND_ID,
        ChatMode.QUOTES_COMMAND_ID,
    }:
        m, s = extract_search_params(query)
        return ParsedQuery(chat_mode=chat_mode, message=m, search_params=s)

    if chat_mode == ChatMode.DB_COMMAND_ID:
        c, m = get_command(query, db_command_to_enum, DBCommand.NONE)
        return ParsedQuery(chat_mode=chat_mode, db_command=c, message=m)

    if chat_mode in {ChatMode.INGEST_COMMAND_ID, ChatMode.SUMMARIZE_COMMAND_ID}:
        c, m = get_command(query, ingest_command_to_enum, IngestCommand.DEFAULT)
        return ParsedQuery(chat_mode=chat_mode, ingest_command=c, message=m)

    if chat_mode == ChatMode.RESEARCH_COMMAND_ID:
        r, m = parse_research_command(query)
        return ParsedQuery(chat_mode=chat_mode, research_params=r, message=m)

    if chat_mode == ChatMode.SHARE_COMMAND_ID:
        s = parse_share_command(query)
        return ParsedQuery(chat_mode=chat_mode, share_params=s)

    if chat_mode == ChatMode.EXPORT_COMMAND_ID:
        e, m = get_command(query, export_command_to_enum, ExportCommand.NONE)
        return ParsedQuery(chat_mode=chat_mode, export_command=e, message=m)

    return ParsedQuery(chat_mode=chat_mode, message=query)
