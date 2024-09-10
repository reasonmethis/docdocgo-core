from utils.chat_state import ChatState
from utils.helpers import (
    DELIMITER80_NONL,
    EXPORT_COMMAND_HELP_MSG,
    format_nonstreaming_answer,
)
from utils.query_parsing import ExportCommand, get_command, get_int, get_int_or_command
from utils.type_utils import INSTRUCT_EXPORT_CHAT_HISTORY, Instruction, Props

REVERSE_COMMAND = "reverse"


def get_exporter_response(chat_state: ChatState) -> Props:
    message = chat_state.message
    subcommand = chat_state.parsed_query.export_command

    if subcommand == ExportCommand.NONE:
        return format_nonstreaming_answer(EXPORT_COMMAND_HELP_MSG)

    if subcommand == ExportCommand.CHAT:
        max_messages = 1000000000
        is_reverse = False
        cmd, rest = get_int_or_command(message, [REVERSE_COMMAND])
        if isinstance(cmd, int):
            max_messages = cmd
            cmd, rest = get_command(rest, [REVERSE_COMMAND])
            if cmd is not None:
                is_reverse = True
            elif rest:  # invalid non-empty command
                return format_nonstreaming_answer(EXPORT_COMMAND_HELP_MSG)
        elif cmd == REVERSE_COMMAND:
            is_reverse = True
            cmd, rest = get_int(rest)
            if cmd is not None:
                max_messages = cmd
            elif rest:  # invalid non-empty command after reverse
                return format_nonstreaming_answer(EXPORT_COMMAND_HELP_MSG)
        elif rest:  # cmd is None but message is not empty (invalid command)
            return format_nonstreaming_answer(EXPORT_COMMAND_HELP_MSG)

        if max_messages <= 0:
            return format_nonstreaming_answer(EXPORT_COMMAND_HELP_MSG)

        # Get and format the last num_messages messages
        msgs = []
        for (user_msg, ai_msg), sources in zip(
            reversed(chat_state.chat_history), reversed(chat_state.sources_history)
        ):
            if len(msgs) >= max_messages:
                break
            if ai_msg is not None or sources:
                ai_msg_full = f"**DDG:** {ai_msg or ''}"
                if sources:
                    tmp = "\n- ".join(sources)
                    ai_msg_full += f"\n\n**SOURCES:**\n\n- {tmp}"
                msgs.append(ai_msg_full)
            if user_msg is not None:
                msgs.append(f"**USER:** {user_msg}")

        # We may have overshot by one message (didn't want to check twice in the loop)
        if len(msgs) > max_messages:
            msgs.pop()

        # Reverse the messages if needed, format them and return along with instructions
        data = f"\n\n{DELIMITER80_NONL}\n\n".join(msgs[:: 1 if is_reverse else -1])
        return format_nonstreaming_answer(
            "I have collected our chat history and sent it to the UI for export."
        ) | {
            "instructions": [Instruction(type=INSTRUCT_EXPORT_CHAT_HISTORY, data=data)],
        }
    raise ValueError(f"Invalid export subcommand: {subcommand}")
