from typing import Any
import os

from enum import Enum
from components.chroma_ddg import ChromaDDG, initialize_client, load_vectorstore
from utils.input import get_choice_from_dict_menu, get_menu_choice
from utils.prepare import DEFAULT_COLLECTION_NAME

DBCommand = Enum("DBCommand", "LIST SWITCH RENAME DELETE EXIT")
menu_main = {
    DBCommand.LIST: "List databases",
    DBCommand.SWITCH: "Switch database",
    DBCommand.RENAME: "Rename database",
    DBCommand.DELETE: "Delete database",
    DBCommand.EXIT: "I'm done here",
}


def manage_dbs(vectorstore: ChromaDDG) -> dict[str, Any]:
    """
    Manage databases
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
        elif choice == DBCommand.SWITCH:
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


def handle_db_command(message: str, vectorstore: ChromaDDG) -> dict[str, Any]:
    """
    Handle a /db command
    """
    if not message:
        return manage_dbs(vectorstore)

    # partial_res = {"needs_print": True}
    try:
        db_dir, collection_name = os.path.split(message)
    except Exception:
        db_dir = collection_name = ""
    if not collection_name:
        print("A valid docs db name must be provided.")
        return {"answer": ""}
        # return partial_res | {"answer": "A valid docs db name must be provided."}
    try:
        if db_dir:
            chroma_client = initialize_client(db_dir)
        else:
            chroma_client = vectorstore._client
        vectorstore = load_vectorstore(collection_name, chroma_client)
    except Exception as e:
        print(f"Error loading requested database: {e}")
        return {"answer": ""}
    print(f"Switching to vector database: {message}")
    return {
        "answer": "",
        "vectorstore": vectorstore,
    }
