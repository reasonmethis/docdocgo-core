import os

from chromadb import Collection

from components.chroma_ddg import ChromaDDG
from utils.chat_state import ChatState
from utils.helpers import (
    DB_COMMAND_HELP_TEMPLATE,
    PRIVATE_COLLECTION_FULL_PREFIX_LENGTH,
    PRIVATE_COLLECTION_PREFIX,
    PRIVATE_COLLECTION_USER_ID_LENGTH,
    format_nonstreaming_answer,
)
from utils.input import get_choice_from_dict_menu, get_menu_choice
from utils.output import format_exception
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.query_parsing import DBCommand
from utils.type_utils import JSONish, OperationMode, Props

menu_main = {
    DBCommand.LIST: "List collections",
    DBCommand.USE: "Switch collection",
    DBCommand.RENAME: "Rename collection",
    DBCommand.DELETE: "Delete collection",
    DBCommand.EXIT: "I'm done here",
}


def get_user_facing_collection_name(collection_name: str) -> str:
    """
    Get the user-facing name of a collection by removing the internal prefix
    containing the user ID, if any.
    """
    return (
        collection_name[PRIVATE_COLLECTION_FULL_PREFIX_LENGTH:]
        if collection_name.startswith(PRIVATE_COLLECTION_PREFIX)
        else collection_name
    )


def construct_full_collection_name(user_id: str | None, collection_name: str) -> str:
    """
    Construct the full collection name from the user ID and the user-facing name.
    """
    return (
        PRIVATE_COLLECTION_PREFIX
        + user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:]
        + collection_name
        if user_id
        else collection_name
    )


def is_user_authorized_for_collection(user_id: str | None, coll_name_full: str) -> bool:
    """
    Check if the user is authorized to access the given collection.
    """
    if not user_id:
        return not coll_name_full.startswith(PRIVATE_COLLECTION_PREFIX)
    return coll_name_full == DEFAULT_COLLECTION_NAME or coll_name_full.startswith(
        PRIVATE_COLLECTION_PREFIX + user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:]
    )


def get_collections(
    vectorstore: ChromaDDG, user_id: str | None, include_default_collection=True
) -> list[Collection]:
    """
    Get the collections for the given user
    """
    collections = vectorstore.client.list_collections()
    if not user_id:
        # Return only public collections
        return [
            c for c in collections if not c.name.startswith(PRIVATE_COLLECTION_PREFIX)
        ]

    if len(user_id) < PRIVATE_COLLECTION_USER_ID_LENGTH:
        raise ValueError(f"Invalid user_id: {user_id}")

    # User's collections are prefixed with:
    prefix = PRIVATE_COLLECTION_PREFIX + user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:]

    if not include_default_collection:
        # Return only the user's collections
        return [c for c in collections if c.name.startswith(prefix)]

    # Return the user's collections and the default collection
    return [
        c
        for c in collections
        if c.name.startswith(prefix) or c.name == DEFAULT_COLLECTION_NAME
    ]


def manage_dbs_console(chat_state: ChatState) -> JSONish:
    """
    Manage collections from the console (using `input`).
    NOTE: In console mode, there's no separation of users.
    """
    while True:
        # Print the menu and get the user's choice
        print()
        command = get_choice_from_dict_menu(menu_main)
        if command == DBCommand.EXIT:
            print("OK, back to the chat.")
            return {"answer": ""}
        elif command == DBCommand.LIST:
            collections = chat_state.vectorstore.client.list_collections()
            print("\nAvailable collections:")
            for i, collection in enumerate(collections):
                print(f"{i+1}. {collection.name}")
        elif command == DBCommand.USE:
            collections = chat_state.vectorstore.client.list_collections()
            collection_names = [collection.name for collection in collections]
            print()
            collection_idx = get_menu_choice(
                collection_names,
                "Enter the number corresponding to the collection you want "
                "to switch to (Enter = Cancel): ",
                default=-1,
            )
            if collection_idx != -1:
                collection_name = collection_names[collection_idx]
                print(f"Switching to collection: {collection_name}")
                return {
                    "answer": "",
                    "vectorstore": chat_state.get_new_vectorstore(collection_name),
                }
        elif command == DBCommand.RENAME:
            if chat_state.vectorstore.name == DEFAULT_COLLECTION_NAME:
                print("You cannot rename the default collection.")
                continue
            print(f"The current collection name is: {chat_state.vectorstore.name}")
            new_name = input(
                "Enter the new name for this collection (Enter = Cancel): "
            )
            if not new_name:
                continue
            try:
                chat_state.vectorstore.rename_collection(new_name)
            except Exception as e:
                print(f"Error renaming collection: {e}")
                continue
            print(f"Collection renamed to: {new_name}")
            return {
                "answer": "",
                "vectorstore": chat_state.get_new_vectorstore(new_name),
            }  # NOTE: can likely just return vectorstore without reinitializing
        elif command == DBCommand.DELETE:
            collections = chat_state.vectorstore.client.list_collections()
            collection_names = [collection.name for collection in collections]
            print()
            collection_idx = get_menu_choice(
                collection_names,
                "Enter the number corresponding to the collection you want "
                "to delete (Enter = Cancel): ",
                default=-1,
            )
            if collection_idx == -1:
                continue
            collection_name = collection_names[collection_idx]
            if collection_name == DEFAULT_COLLECTION_NAME:
                print("You cannot delete the default collection.")
                continue
            if collection_name == chat_state.vectorstore.name:
                print("You cannot delete the currently selected collection.")
                continue
            ans = input(
                f"Are you sure you want to delete the collection {collection_name}? [y/N] "
            )
            if ans == "y":
                chat_state.vectorstore.delete_collection(collection_name)
                print(f"Collection {collection_name} deleted.")
                return {"answer": ""}


def sort_collection_names(
    coll_names_as_shown: list[str], coll_names_full: list[str]
) -> tuple[list[str], list[str]]:
    # Sort the collections by name as shown, but put the default collection first
    coll_name_pairs = sorted(
        zip(coll_names_as_shown, coll_names_full),
        key=lambda pair: (pair[1] != DEFAULT_COLLECTION_NAME, pair[0]),
    )
    return tuple(zip(*coll_name_pairs))


def handle_db_command_with_subcommand(chat_state: ChatState) -> Props:
    command = chat_state.parsed_query.db_command
    value = chat_state.parsed_query.message

    collections = get_collections(chat_state.vectorstore, chat_state.user_id)
    coll_names_full = [c.name for c in collections]
    coll_names_as_shown = list(map(get_user_facing_collection_name, coll_names_full))
    coll_names_as_shown, coll_names_full = sort_collection_names(
        coll_names_as_shown, coll_names_full
    )

    def get_available_dbs_str() -> str:
        tmp = "\n".join([f"{i+1}. {n}" for i, n in enumerate(coll_names_as_shown)])
        return f"Available collections:\n\n{tmp}"

    def get_db_not_found_str(name: str) -> str:
        return f"Collection {name} not found. {get_available_dbs_str()}"

    if command == DBCommand.LIST:
        return format_nonstreaming_answer(
            f"{get_available_dbs_str()}\n\n"
            "**Tip:** To switch to collection number N, type `/db use N`."
        )

    if command == DBCommand.USE:
        if not value:
            return format_nonstreaming_answer(
                get_available_dbs_str()
                + "\n\nTo switch collections, you must provide the name or number "
                "of the collection to switch to. Example:\n"
                "```\n/db use 3\n```"
            )

        # Get the index of the collection to switch to
        try:
            idx = coll_names_as_shown.index(value)
        except ValueError:
            try:
                # See if the user provided an index directly instead of a name
                idx = int(value) - 1
                if idx < 0 or idx >= len(coll_names_as_shown):
                    raise ValueError
                value = coll_names_as_shown[idx]
            except ValueError:
                return format_nonstreaming_answer(get_db_not_found_str(value))

        return format_nonstreaming_answer(f"Switched to collection: `{value}`.") | {
            "vectorstore": chat_state.get_new_vectorstore(coll_names_full[idx]),
        }

    if command == DBCommand.RENAME:
        if chat_state.vectorstore.name == DEFAULT_COLLECTION_NAME:
            return format_nonstreaming_answer(
                "You cannot rename the default collection."
            )
        if not value:
            return format_nonstreaming_answer(
                "To rename the current collection, you must provide a new name. Example:\n"
                "```\n/db rename awesome-new-name\n```"
            )
        # if value == DEFAULT_COLLECTION_NAME:
        #     return format_nonstreaming_answer("You cannot rename a collection to the default name.")
        if not chat_state.user_id and value.startswith(PRIVATE_COLLECTION_PREFIX):
            return format_nonstreaming_answer(
                f"A public collection's name cannot start with `{PRIVATE_COLLECTION_PREFIX}`."
            )

        # Get the full name of the collection to rename to
        if value == DEFAULT_COLLECTION_NAME:
            # Will usually fail, but ok if admin has deleted the default collection
            new_full_name = DEFAULT_COLLECTION_NAME
        else:
            new_full_name = construct_full_collection_name(chat_state.user_id, value)

        # Rename the collection
        try:
            chat_state.vectorstore.rename_collection(new_full_name)
        except Exception as e:
            return format_nonstreaming_answer(
                f"Error renaming collection:\n```\n{format_exception(e)}\n```"
            )

        return format_nonstreaming_answer(f"Collection renamed to: {value}") | {
            "vectorstore": chat_state.get_new_vectorstore(new_full_name),
        }

    if command == DBCommand.DELETE:
        if not value:
            return format_nonstreaming_answer(
                get_available_dbs_str()
                + "\n\nTo delete a collection, you must provide the name of "
                "the collection to delete, a list of collection numbers, or "
                "the --current (-c) flag to delete the current collection. Examples:\n"
                "```\n/db delete my-temp-db\n/db delete 2, 4, 19\n"
                "/db delete 19\n/db delete -c\n```"
            )

        if value == "-c" or value == "--current":
            value = get_user_facing_collection_name(chat_state.vectorstore.name)

        if value == DEFAULT_COLLECTION_NAME:
            return format_nonstreaming_answer(
                "You cannot delete the default collection."
            )

        # Admin can delete the default collection by providing the password
        pwd = os.getenv("BYPASS_SETTINGS_RESTRICTIONS_PASSWORD")
        if value == f"--default {pwd}" and pwd:
            value = DEFAULT_COLLECTION_NAME

        # NOTE: the functionality below requires allow_reset=True in the settings
        # or an ALLOW_RESET env variable **on the server**.
            
        # # Admin can also reset the whole db by providing the password
        # if value == f"--reset {pwd}" and pwd:
        #     chat_state.vectorstore.client.reset()
        #     return format_nonstreaming_answer("The entire database has been reset.")

        # Get the full name(s) of the collection(s) to delete
        try:
            full_names = [coll_names_full[coll_names_as_shown.index(value)]]
        except ValueError:
            try:
                # See if the user provided index(es) directly instead of a name
                if "-" in value:
                    # Admin can delete a range of collections by providing the password
                    if not value.endswith(f" {pwd}") or not pwd:
                        raise ValueError
                    leftright = value[: -len(pwd) - 1].split("-")
                    if len(leftright) != 2:
                        raise ValueError
                    min_idx, max_idx = int(leftright[0]) - 1, int(leftright[1]) - 1
                    if min_idx < 1 or max_idx >= len(coll_names_as_shown):
                        raise ValueError
                    idxs = list(range(min_idx, max_idx + 1))
                else:
                    # Usual case: see if we got a comma-separated list of indexes
                    idxs = [int(s) - 1 for s in value.split(",")]

                    # Check that all idxs are valid
                    if any(idx < 1 or idx >= len(coll_names_as_shown) for idx in idxs):
                        raise ValueError  # idx == 0 not allowed, it's the default collection

                # One last check:
                if not idxs:
                    raise ValueError

                # Get the full names of the collections
                full_names = [coll_names_full[idx] for idx in idxs]
            except ValueError:
                return format_nonstreaming_answer(get_db_not_found_str(value))

        # Delete the collection(s)
        for full_name in full_names:
            chat_state.vectorstore.delete_collection(full_name)

        # Form answer, and - if the current collection was deleted - initiate a switch
        names_as_shown = [
            get_user_facing_collection_name(full_name) for full_name in full_names
        ]
        s_or_no_s = "s" if len(names_as_shown) > 1 else ""
        ans = format_nonstreaming_answer(
            f"Collection{s_or_no_s} `{', '.join(names_as_shown)}` deleted."
        )
        if any(full_name == chat_state.vectorstore.name for full_name in full_names):
            ans["vectorstore"] = chat_state.get_new_vectorstore(DEFAULT_COLLECTION_NAME)

        return ans

    # Should never happen
    raise ValueError(f"Invalid /db subcommand: {command}")

    # Currently unused logic for switching to a db in a different directory

    # try:
    #     db_dir, collection_name = os.path.split(value)
    # except Exception:
    #     db_dir = collection_name = ""
    # if not collection_name:
    #     return partial_res | {"answer": "A valid docs db name must be provided."}
    # try:
    #     if db_dir:
    #         chroma_client = initialize_client(db_dir)
    #     else:
    #         chroma_client = vectorstore._client
    #     vectorstore = load_vectorstore(collection_name, chroma_client)
    # except Exception as e:
    #     print(f"Error loading requested collection: {e}")
    #     return {"answer": ""}
    # print(f"Switching to vector collection: {message}")
    # return {
    #     "answer": "",
    #     "vectorstore": vectorstore,
    # }


def handle_db_command(chat_state: ChatState) -> Props:
    """
    Handle a /db command
    """

    # Handle /db with no valid subcommand
    if chat_state.parsed_query.db_command == DBCommand.NONE:
        if chat_state.operation_mode == OperationMode.CONSOLE:
            return manage_dbs_console(chat_state)
        return format_nonstreaming_answer(
            DB_COMMAND_HELP_TEMPLATE.format(current_db=chat_state.vectorstore.name)
        )

    # Handle the command
    return handle_db_command_with_subcommand(chat_state)
