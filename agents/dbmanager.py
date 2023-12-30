from enum import Enum
from typing import Any

from chromadb import Collection

from components.chroma_ddg import ChromaDDG, load_vectorstore
from utils.chat_state import ChatState
from utils.helpers import (
    DB_COMMAND_HELP_TEMPLATE,
    PRIVATE_COLLECTION_FULL_PREFIX_LENGTH,
    PRIVATE_COLLECTION_PREFIX,
    PRIVATE_COLLECTION_USER_ID_LENGTH,
)
from utils.input import get_choice_from_dict_menu, get_menu_choice
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.type_utils import JSONish, OperationMode

DBCommand = Enum("DBCommand", "LIST USE RENAME DELETE EXIT")
menu_main = {
    DBCommand.LIST: "List collections",
    DBCommand.USE: "Switch collection",
    DBCommand.RENAME: "Rename collection",
    DBCommand.DELETE: "Delete collection",
    DBCommand.EXIT: "I'm done here",
}
db_command_to_enum = {
    "list": DBCommand.LIST,
    "use": DBCommand.USE,
    "rename": DBCommand.RENAME,
    "delete": DBCommand.DELETE,
    "exit": DBCommand.EXIT,
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


def manage_dbs_console(vectorstore: ChromaDDG) -> JSONish:
    """
    Manage collections from the console (using `input`).
    NOTE: In console mode, there's no separation of users.
    """
    while True:
        # Print the menu and get the user's choice
        print()
        choice = get_choice_from_dict_menu(menu_main)
        if choice == DBCommand.EXIT:
            print("OK, back to the chat.")
            return {"answer": ""}
        elif choice == DBCommand.LIST:
            collections = vectorstore._client.list_collections()
            print("\nAvailable collections:")
            for i, collection in enumerate(collections):
                print(f"{i+1}. {collection.name}")
        elif choice == DBCommand.USE:
            collections = vectorstore._client.list_collections()
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
                    "vectorstore": load_vectorstore(
                        collection_name, vectorstore._client
                    ),
                }
        elif choice == DBCommand.RENAME:
            if vectorstore.name == DEFAULT_COLLECTION_NAME:
                print("You cannot rename the default collection.")
                continue
            print(f"The current collection name is: {vectorstore.name}")
            new_name = input(
                "Enter the new name for this collection (Enter = Cancel): "
            )
            if not new_name:
                continue
            try:
                vectorstore.rename_collection(new_name)
            except Exception as e:
                print(f"Error renaming collection: {e}")
                continue
            print(f"Collection renamed to: {new_name}")
            return {
                "answer": "",
                "vectorstore": load_vectorstore(new_name, vectorstore._client),
            }  # NOTE: can likely just return vectorstore without reinitializing
        elif choice == DBCommand.DELETE:
            collections = vectorstore._client.list_collections()
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
            if collection_name == vectorstore.name:
                print("You cannot delete the currently selected collection.")
                continue
            ans = input(
                f"Are you sure you want to delete the collection {collection_name}? [y/N] "
            )
            if ans == "y":
                vectorstore.delete_collection(collection_name)
                print(f"Collection {collection_name} deleted.")
                return {"answer": ""}


def format_answer(answer):
    return {"skip_history": True, "answer": answer, "needs_print": True}


def handle_db_command_with_subcommand(
    vectorstore: ChromaDDG, choice: DBCommand, value: str, user_id: str | None
) -> dict[str, Any]:
    collections = get_collections(vectorstore, user_id)
    coll_names_full = [c.name for c in collections]
    coll_names_as_shown = list(map(get_user_facing_collection_name, coll_names_full))

    def get_available_dbs_str() -> str:
        tmp = "\n".join([f"{i+1}. {n}" for i, n in enumerate(coll_names_as_shown)])
        return f"Available collections:\n\n{tmp}"

    def get_db_not_found_str(name: str) -> str:
        return f"Collection {name} not found. {get_available_dbs_str()}"

    if choice == DBCommand.LIST:
        return format_answer(get_available_dbs_str())

    if choice == DBCommand.USE:
        if not value:
            return format_answer(
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
                return format_answer(get_db_not_found_str(value))

        return format_answer(f"Switched to collection: `{value}`.") | {
            "vectorstore": load_vectorstore(coll_names_full[idx], vectorstore.client),
        }

    if choice == DBCommand.RENAME:
        if vectorstore.name == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot rename the default collection.")
        if not value:
            return format_answer(
                "To rename the current collection, you must provide a new name. Example:\n"
                "```\n/db rename awesome-new-name\n```"
            )
        if value == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot rename a collection to the default name.")
        if not user_id and value.startswith(PRIVATE_COLLECTION_PREFIX):
            return format_answer(
                f"A public collection's name cannot start with `{PRIVATE_COLLECTION_PREFIX}`."
            )

        new_full_name = construct_full_collection_name(user_id, value)
        try:
            vectorstore.rename_collection(new_full_name)
        except Exception as e:
            return format_answer(f"Error renaming collection:\n```\n{e}\n```")

        return format_answer(f"Collection renamed to: {value}") | {
            "vectorstore": load_vectorstore(new_full_name, vectorstore.client),
        }

    if choice == DBCommand.DELETE:
        if not value:
            return format_answer(
                get_available_dbs_str()
                + "\n\nTo delete a collection, you must provide the name of "
                "the collection to delete. Example:\n"
                "```\n/db delete my-temp-db\n```"
            )
        if value == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot delete the default collection.")

        curr_coll_name_as_shown = get_user_facing_collection_name(vectorstore.name)
        if value == "-c" or value == "--current":
            value = curr_coll_name_as_shown

        # Get the full name of the collection to delete
        try:
            full_name = coll_names_full[coll_names_as_shown.index(value)]
        except ValueError:
            return format_answer(get_db_not_found_str(value))

        # Delete the collection
        vectorstore.delete_collection(full_name)

        # Form answer, and - if the current collection was deleted - indicate a switch
        ans = format_answer(f"Collection `{value}` deleted.")
        if full_name == vectorstore.name:
            ans |= {
                "vectorstore": load_vectorstore(
                    DEFAULT_COLLECTION_NAME, vectorstore.client
                )
            }

        return ans

    # Should never happen
    raise ValueError(f"Invalid command: {choice}")

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


def get_db_subcommand_from_split_message(words: list[str]) -> DBCommand | None:
    """
    Get the subcommand from a split message
    """
    try:
        return db_command_to_enum[words[0]]
    except (KeyError, IndexError):
        return None


def handle_db_command(chat_state: ChatState) -> JSONish:
    """
    Handle a /db command
    """

    vectorstore = chat_state.vectorstore
    words = chat_state.message.split()

    # Handle /db with no arguments
    if not words:
        if chat_state.operation_mode == OperationMode.CONSOLE:
            return manage_dbs_console(vectorstore)
        return format_answer(
            DB_COMMAND_HELP_TEMPLATE.format(current_db=vectorstore.name)
        )

    # Determine the command type and value
    if not (choice := get_db_subcommand_from_split_message(words)):
        return format_answer(
            DB_COMMAND_HELP_TEMPLATE.format(current_db=vectorstore.name)
        )

    value = words[1] if len(words) > 1 else ""

    # Handle the command
    return handle_db_command_with_subcommand(
        vectorstore, choice, value, chat_state.user_id
    )
