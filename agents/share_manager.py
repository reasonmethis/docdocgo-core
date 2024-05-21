from agents.dbmanager import get_access_role, is_main_owner
from utils.chat_state import ChatState
from utils.helpers import SHARE_COMMAND_HELP_MSG, format_nonstreaming_answer
from utils.prepare import DOMAIN_NAME_FOR_SHARING
from utils.query_parsing import ShareCommand, ShareRevokeSubCommand
from utils.type_utils import (
    AccessCodeSettings,
    AccessCodeType,
    AccessRole,
    Props,
)

share_type_to_access_role = {
    ShareCommand.EDITOR: AccessRole.EDITOR,
    ShareCommand.VIEWER: AccessRole.VIEWER,
    ShareCommand.OWNER: AccessRole.OWNER,
}


def handle_share_command(chat_state: ChatState) -> Props:
    """Handle the /share command."""
    share_params = chat_state.parsed_query.share_params
    if share_params.share_type == ShareCommand.NONE:
        return format_nonstreaming_answer(SHARE_COMMAND_HELP_MSG)

    # Check that the user is an owner
    access_role = get_access_role(chat_state)
    if access_role.value < AccessRole.OWNER.value:
        return format_nonstreaming_answer(
            "Apologies, you don't have owner-level access to this collection. "
            f"Your current access level: {access_role.name.lower()}."
        )
    # NOTE: this introduces redundant fetching of metadata (in get_access_role
    # and save_access_code_settings. Can optimize later.

    if share_params.share_type in (
        ShareCommand.EDITOR,
        ShareCommand.VIEWER,
        ShareCommand.OWNER,
    ):
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
            access_role=share_type_to_access_role[share_params.share_type],
        )
        chat_state.save_access_code_settings(
            access_code=share_params.access_code,
            access_code_settings=access_code_settings,
        )

        # Form share link
        link = (
            f"{DOMAIN_NAME_FOR_SHARING}?collection={chat_state.vectorstore.name}"
            f"&access_code={share_params.access_code}"
        )

        # Return the response with the share link
        return format_nonstreaming_answer(
            "The current collection has been shared. Here's the link you can send "
            "to the people you want to grant access to:\n\n"
            f"```\n{link}\n```"
        )

    if share_params.share_type == ShareCommand.REVOKE:
        collection_permissions = chat_state.get_collection_permissions()
        match share_params.revoke_type:
            case ShareRevokeSubCommand.ALL_CODES:
                collection_permissions.access_code_to_settings = {}
                ans = "All access codes have been revoked."

            case ShareRevokeSubCommand.ALL_USERS:
                # If user is not the main owner, don't delete their owner status
                saved_entries = {}
                if is_main_owner(chat_state):
                    ans = "All users except you have been revoked."
                else:
                    try:
                        saved_entries[chat_state.user_id] = (
                            collection_permissions.user_id_to_settings[
                                chat_state.user_id
                            ]
                        )
                        ans = (
                            "All users except the main owner and you have been revoked."
                        )
                    except KeyError:
                        ans = "All users except the main owner have been revoked (including you)."

                # Clear all user settings except saved_entries
                collection_permissions.user_id_to_settings = saved_entries

            case ShareRevokeSubCommand.CODE:
                code = (share_params.code_or_user_to_revoke or "").strip()
                if not code:
                    return format_nonstreaming_answer(
                        "Apologies, you need to specify an access code to revoke."
                    )
                try:
                    collection_permissions.access_code_to_settings.pop(code)
                    ans = "The access code has been revoked."
                except KeyError:
                    return format_nonstreaming_answer(
                        "Apologies, the access code you specified doesn't exist."
                    )

            case ShareRevokeSubCommand.USER:
                user_id = (share_params.code_or_user_to_revoke or "").strip()
                if not user_id:
                    return format_nonstreaming_answer(
                        "Apologies, you need to specify a user to revoke."
                    )
                if user_id == "public":
                    user_id = ""
                try:
                    print(collection_permissions.user_id_to_settings)
                    collection_permissions.user_id_to_settings.pop(user_id)
                    print(collection_permissions.user_id_to_settings)
                    ans = "The user has been revoked."
                except KeyError:
                    return format_nonstreaming_answer(
                        "Apologies, the user you specified doesn't have a stored access role."
                    )
            case _:
                return format_nonstreaming_answer(
                    "Apologies, Dmitriy hasn't implemented this share subcommand for me yet."
                )

        chat_state.save_collection_permissions(
            collection_permissions, use_cached_metadata=True
        )
        return format_nonstreaming_answer(ans)

    return format_nonstreaming_answer(
        "Apologies, Dmitriy hasn't implemented this share subcommand for me yet."
    )
