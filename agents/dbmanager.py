from enum import Enum

from components.chroma_ddg import ChromaDDG, load_vectorstore
from utils.helpers import DB_COMMAND_HELP_TEMPLATE
from utils.input import get_choice_from_dict_menu, get_menu_choice
from utils.prepare import DEFAULT_COLLECTION_NAME
from utils.type_utils import ChatState, JSONish, OperationMode

DBCommand = Enum("DBCommand", "LIST USE RENAME DELETE EXIT")
menu_main = {
    DBCommand.LIST: "List databases",
    DBCommand.USE: "Switch database",
    DBCommand.RENAME: "Rename database",
    DBCommand.DELETE: "Delete database",
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
    Manage databases from the console (using `input`)
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
            print("\nAvailable databases:")
            for i, collection in enumerate(collections):
                print(f"{i+1}. {collection.name}")
        elif choice == DBCommand.USE:
            collections = vectorstore._client.list_collections()
            collection_names = [collection.name for collection in collections]
            print()
            collection_idx = get_menu_choice(
                collection_names,
                "Enter the number corresponding to the database you want "
                "to switch to (Enter = Cancel): ",
                default=-1,
            )
            if collection_idx != -1:
                collection_name = collection_names[collection_idx]
                print(f"Switching to database: {collection_name}")
                return {
                    "answer": "",
                    "vectorstore": load_vectorstore(
                        collection_name, vectorstore._client
                    ),
                }
        elif choice == DBCommand.RENAME:
            if vectorstore.name == DEFAULT_COLLECTION_NAME:
                print("You cannot rename the default database.")
                continue
            print(f"The current database name is: {vectorstore.name}")
            new_name = input("Enter the new name for this database (Enter = Cancel): ")
            if not new_name:
                continue
            try:
                vectorstore._collection.modify(name=new_name)
            except Exception as e:
                print(f"Error renaming database: {e}")
                continue
            print(f"Database renamed to: {new_name}")
            return {
                "answer": "",
                "vectorstore": load_vectorstore(new_name, vectorstore._client),
            }
        elif choice == DBCommand.DELETE:
            collections = vectorstore._client.list_collections()
            collection_names = [collection.name for collection in collections]
            print()
            collection_idx = get_menu_choice(
                collection_names,
                "Enter the number corresponding to the database you want "
                "to delete (Enter = Cancel): ",
                default=-1,
            )
            if collection_idx == -1:
                continue
            collection_name = collection_names[collection_idx]
            if collection_name == DEFAULT_COLLECTION_NAME:
                print("You cannot delete the default database.")
                continue
            if collection_name == vectorstore.name:
                print("You cannot delete the currently selected database.")
                continue
            ans = input(
                f"Are you sure you want to delete the database {collection_name}? [y/N] "
            )
            if ans == "y":
                vectorstore._client.delete_collection(name=collection_name)
                print(f"Database {collection_name} deleted.")
                return {"answer": ""}


def format_answer(answer):
    return {"skip_history": True, "answer": answer}


def manage_dbs_non_console(
    vectorstore: ChromaDDG, choice: DBCommand, value: str
) -> JSONish:
    collections = vectorstore._client.list_collections()
    collection_names = [c.name for c in collections]

    def get_available_dbs_str() -> str:
        tmp = "\n".join([f"{i+1}. {n}" for i, n in enumerate(collection_names)])
        return f"Available databases:\n\n{tmp}"

    def get_db_not_found_str(name: str) -> str:
        return f"Database {name} not found. {get_available_dbs_str()}"

    if choice == DBCommand.LIST:
        return format_answer(get_available_dbs_str())

    if choice == DBCommand.USE:
        if not value:
            return format_answer(
                "To switch databases, you must provide the name of the database to switch to. Example:\n"
                "```\n/db use my-notes-db\n```"
            )

        if value not in collection_names:
            return format_answer(get_db_not_found_str(value))

        return format_answer(f"Switched to database: {value}") | {
            "vectorstore": load_vectorstore(value, vectorstore._client),
        }

    if choice == DBCommand.RENAME:
        if vectorstore.name == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot rename the default database.")
        if not value:
            return format_answer(
                "To rename the current database, you must provide a new name. Example:\n"
                "```\n/db rename awesome-new-name\n```"
            )

        try:
            vectorstore._collection.modify(name=value)
        except Exception as e:
            return format_answer(f"Error renaming database:\n```\n{e}\n```")

        return format_answer(f"Database renamed to: {value}") | {
            "vectorstore": load_vectorstore(value, vectorstore._client),
        }

    if choice == DBCommand.DELETE:
        if not value:
            return format_answer(
                "To delete a database, you must provide the name of the database to delete. Example:\n"
                "```\n/db delete my-temp-db\n```"
            )
        if value == DEFAULT_COLLECTION_NAME:
            return format_answer("You cannot delete the default database.")
        if value == vectorstore.name:
            return format_answer("You cannot delete the currently selected database.")
        if value not in collection_names:
            return format_answer(get_db_not_found_str(value))

        vectorstore._client.delete_collection(name=value)
        return format_answer(f"Database {value} deleted.")

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
    #     print(f"Error loading requested database: {e}")
    #     return {"answer": ""}
    # print(f"Switching to vector database: {message}")
    # return {
    #     "answer": "",
    #     "vectorstore": vectorstore,
    # }


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
    try:
        choice = db_command_to_enum[words[0]]
    except KeyError:
        return format_answer(
            DB_COMMAND_HELP_TEMPLATE.format(current_db=vectorstore.name)
        )

    value = words[1] if len(words) > 1 else ""

    # Handle the command
    return manage_dbs_non_console(vectorstore, choice, value)
