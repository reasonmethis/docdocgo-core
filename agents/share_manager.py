import os

from utils.chat_state import ChatState
from utils.helpers import SHARE_COMMAND_HELP_MSG, format_nonstreaming_answer
from utils.query_parsing import ShareCommand
from utils.type_utils import (
    AccessCodeSettings,
    AccessCodeType,
    AccessRole,
    Props,
)


def handle_share_command(chat_state: ChatState) -> Props:
    """Handle the /share command."""
    share_params = chat_state.parsed_query.share_params
    if share_params.share_type == ShareCommand.NONE:
        return format_nonstreaming_answer(SHARE_COMMAND_HELP_MSG)

    if share_params.share_type in (ShareCommand.EDITOR, ShareCommand.VIEWER):
        # Check that the access code is not empty
        if (access_code := share_params.access_code) is None:
            return format_nonstreaming_answer(
                "Apologies, you need to specify an access code."
                f"\n\n{SHARE_COMMAND_HELP_MSG}"
            )

        # Check that the access code type is not empty
        if (code_type := share_params.access_code_type) is None:
            return format_nonstreaming_answer(
                "Apologies, you need to specify an access code type."
                f"\n\n{SHARE_COMMAND_HELP_MSG}"
            )
        if code_type != AccessCodeType.NEED_ALWAYS:
            return format_nonstreaming_answer(
                "Apologies, Dmitriy hasn't implemented this code type for me yet."
            )

        # Check that the access code contains only letters and numbers
        if not access_code.isalnum():
            return format_nonstreaming_answer(
                "Apologies, the access code can only contain letters and numbers."
            )

        # Save the access code and its settings
        access_code_settings = AccessCodeSettings(
            code_type=code_type,
            access_role=AccessRole.EDITOR
            if share_params.share_type == ShareCommand.EDITOR
            else AccessRole.VIEWER,
        )
        chat_state.save_access_code_settings(
            access_code=share_params.access_code,
            access_code_settings=access_code_settings,
        )

        # Form share link
        domain = os.getenv("DOMAIN_NAME_FOR_SHARING", "https://docdocgo.streamlit.app")
        link = (
            f"{domain}?collection={chat_state.vectorstore.name}"
            f"&access_code={share_params.access_code}"
        )

        # Return the response with the share link
        return format_nonstreaming_answer(
            "The current collection has been shared. Here's the link you can send "
            "to the people you want to grant access to:\n\n"
            f"```\n{link}\n```"
        )
    
    return format_nonstreaming_answer(
        "Apologies, Dmitriy hasn't implemented this share type for me yet."
    )
