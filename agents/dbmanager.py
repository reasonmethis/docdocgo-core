from enum import Enum

from components.chroma_ddg import ChromaDDG, load_vectorstore
from utils.chat_state import ChatState
from utils.helpers import DB_COMMAND_HELP_TEMPLATE
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


def manage_dbs_console(vectorstore: ChromaDDG) -> JSONish:
    """
    Manage collections from the console (using `input`)
    """
    while True:
        # Print the menu and get the user's choice
        print()
        if (choice := get_choice_from_dict_menu(menu_main)) == DBCommand.EXIT:
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
            } # NOTE: can likely just return vectorstore without reinitializing
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
    vectorstore: ChromaDDG, choice: DBCommand, value: str
) -> JSONish:
    collections = vectorstore._client.list_collections()
    collection_names = [c.name for c in collections]

    def get_available_dbs_str() -> str:
        tmp = "\n".join([f"{i+1}. {n}" for i, n in enumerate(collection_names)])
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

        if value not in collection_names:
            try:
                idx = int(value) - 1
                if idx < 0:
                    raise ValueError
                value = collection_names[idx]
            except (ValueError, IndexError):
                return format_answer(get_db_not_found_str(value))

        return format_answer(f"Switched to collection: `{value}`") | {
            "vectorstore": load_vectorstore(value, vectorstore._client),
        }

    if choice == DBCommand.RENAME:
        if vectorstore.name == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot rename the default collection.")
        if not value:
            return format_answer(
                "To rename the current collection, you must provide a new name. Example:\n"
                "```\n/db rename awesome-new-name\n```"
            )

        try:
            vectorstore.rename_collection(value)
        except Exception as e:
            return format_answer(f"Error renaming collection:\n```\n{e}\n```")

        return format_answer(f"Collection renamed to: {value}") | {
            "vectorstore": load_vectorstore(value, vectorstore._client),
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
        if value == vectorstore.name:
            return format_answer("You cannot delete the currently selected collection.")
        if value not in collection_names:
            return format_answer(get_db_not_found_str(value))

        vectorstore.delete_collection(value)
        return format_answer(f"Collection {value} deleted.")

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
    return handle_db_command_with_subcommand(vectorstore, choice, value)
