from utils.chat_state import ChatState
from utils.helpers import DELIMITER20
from utils.query_parsing import ExportCommand, get_int
from utils.type_utils import INSTRUCT_EXPORT_CHAT_HISTORY, Instruction, Props

EXPORTER_HELP_MSG = """\
To export your conversation, use the command:

```markdown
/ex chat <number of past messages>
```

If the number of past messages is not specified, the entire conversation will be exported.
"""


def get_exporter_response(chat_state: ChatState) -> Props:
    message = chat_state.message
    subcommand = chat_state.parsed_query.export_command

    if subcommand == ExportCommand.NONE:
        return {"answer": EXPORTER_HELP_MSG}

    if subcommand == ExportCommand.CHAT:
        if not message:
            num_messages = 1000000000
        else:
            num_messages, rest = get_int(message)
            if num_messages is None:
                return {"answer": EXPORTER_HELP_MSG}

        msgs = []
        for i, ((user_msg, ai_msg), sources) in enumerate(
            zip(reversed(chat_state.chat_history), reversed(chat_state.sources_history))
        ):
            if i >= num_messages:
                break
            if user_msg is not None:
                msgs.append(f"**USER:** {user_msg}")
            if ai_msg is not None or sources:
                ai_msg_full = f"**DDG:** {ai_msg or ''}"
                if sources:
                    tmp = "\n- ".join(sources)
                    ai_msg_full += f"\n\n**SOURCES:**\n\n- {tmp}"
                msgs.append(ai_msg_full)

        delimiter = f"\n\n{DELIMITER20}\n\n"
        return {
            "answer": "I have collected our chat history and sent it to the UI for export.",
            "instructions": [
                Instruction(
                    type=INSTRUCT_EXPORT_CHAT_HISTORY, data=delimiter.join(msgs[::-1])
                )
            ],
        }
    raise ValueError(f"Invalid export subcommand: {subcommand}")
