import os
from datetime import datetime, timezone

from chromadb import Collection
from icecream import ic

from utils.chat_state import ChatState
from utils.helpers import (
    DB_COMMAND_HELP_TEMPLATE,
    DB_CREATED_AT_TIMESTAMP_FORMAT,
    PRIVATE_COLLECTION_FULL_PREFIX_LENGTH,
    PRIVATE_COLLECTION_PREFIX,
    PRIVATE_COLLECTION_PREFIX_LENGTH,
    PRIVATE_COLLECTION_USER_ID_LENGTH,
    format_nonstreaming_answer,
    parse_timestamp,
)
from utils.input import get_choice_from_dict_menu, get_menu_choice
from utils.prepare import (
    BYPASS_SETTINGS_RESTRICTIONS_PASSWORD,
    DEFAULT_COLLECTION_NAME,
    get_logger,
)
from utils.query_parsing import DBCommand
from utils.type_utils import (
    INSTRUCT_CACHE_ACCESS_CODE,
    AccessRole,
    CollectionUserSettings,
    Instruction,
    OperationMode,
    Props,
)

logger = get_logger()

RUN_LIST_FIRST_MSG = (
    "To prevent deletion of the wrong collection, deleting "
    "collections by their numbers is only allowed after running `/db list` first."
)

menu_main = {
    DBCommand.LIST: "List collections",
    DBCommand.USE: "Switch collection",
    DBCommand.RENAME: "Rename collection",
    DBCommand.DELETE: "Delete collection",
    DBCommand.EXIT: "I'm done here",
}


def get_short_user_id(user_id: str | None) -> str | None:
    """
    Get the last PRIVATE_COLLECTION_USER_ID_LENGTH characters of the user ID.
    """
    return user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:] if user_id else None


def get_main_owner_user_id(collection_name: str) -> str | None:
    """
    Get the user ID of the native owner of a collection. If the collection is public,
    return None.
    """
    if collection_name.startswith(PRIVATE_COLLECTION_PREFIX):
        return collection_name[
            PRIVATE_COLLECTION_PREFIX_LENGTH:PRIVATE_COLLECTION_FULL_PREFIX_LENGTH
        ]


def is_main_owner(chat_state: ChatState, collection_name: str | None = None) -> bool:
    """
    Check if the user is the main owner of the collection.
    """
    collection_name = collection_name or chat_state.vectorstore.name
    return get_main_owner_user_id(collection_name) == chat_state.user_id


def get_user_facing_collection_name(user_id: str | None, collection_name: str) -> str:
    """
    Get the user-facing name of a collection by removing the internal prefix
    containing the user ID, if any. The prefix is removed only if the user ID
    matches the one in the collection name.
    """
    # Old collections: u-abcdef<name>, new collections: u-abcdef-<name>
    return (
        collection_name[PRIVATE_COLLECTION_FULL_PREFIX_LENGTH:].lstrip("-")
        if collection_name.startswith(PRIVATE_COLLECTION_PREFIX)
        and user_id == get_main_owner_user_id(collection_name)
        else collection_name
    )


def get_full_collection_name(user_id: str | None, collection_name: str) -> str:
    """
    Construct the full collection name from the user ID and the user-facing name.
    """
    return (
        f"{PRIVATE_COLLECTION_PREFIX}{get_short_user_id(user_id)}" f"-{collection_name}"
        if user_id
        else collection_name
    )
    # NOTE: get_short_user_id is redundant but just to be safe


def get_access_role(
    chat_state: ChatState,
    coll_name_full: str | None = None,
    access_code: str | None = None,
) -> AccessRole:
    """
    Get the access status for the current user to the current or specified collection.

    Warning: it tries to avoid making a db request and, if possible, determines the
    access role based on the collection's name. As a result, it will return OWNER for
    a non-existent collection "hjdfyuirewncx" just because it doesn't start with
    PRIVATE_COLLECTION_PREFIX.
    """
    # TODO: can probably eliminate the need for fetching metadata in cases where
    # all we need is the user's access role to be viewer and that's already stored in
    # chat_state.
    coll_name_full = coll_name_full or chat_state.collection_name

    # The default collection is always accessible in read-only mode
    if coll_name_full == DEFAULT_COLLECTION_NAME:
        admin_pwd = os.getenv("BYPASS_SETTINGS_RESTRICTIONS_PASSWORD")
        if admin_pwd and access_code == admin_pwd:
            return AccessRole.OWNER
        return AccessRole.VIEWER

    # Public collections are always accessible
    if not coll_name_full.startswith(PRIVATE_COLLECTION_PREFIX):
        return AccessRole.OWNER

    # Check if it's the user's own collection
    if chat_state.user_id and coll_name_full.startswith(
        PRIVATE_COLLECTION_PREFIX
        + chat_state.user_id[-PRIVATE_COLLECTION_USER_ID_LENGTH:]
    ):
        return AccessRole.OWNER

    # If access code was used previously, retrieve access role from chat_state
    cached_access_role = chat_state.get_cached_access_role(coll_name_full)

    # If access code is cached, use it if no new access code is provided
    if access_code is None:
        access_code = chat_state.get_cached_access_code(coll_name_full)
        print(
            access_code, chat_state.user_id, chat_state._access_code_by_coll_by_user_id
        )

    # If no access code is being used, trust the stored access role to avoid fetching
    # metadata. It's possible that a higher role was assigned to the user during this
    # session, but it's not worth the extra request to the server to check, since the
    # user can always reload the page to get a new session.
    if cached_access_role.value > AccessRole.NONE.value and access_code is None:
        return cached_access_role

    # If can't be authorized with the simple checks above, check the collection's metadata
    collection_permissions = chat_state.get_collection_permissions(coll_name_full)

    user_settings = collection_permissions.get_user_settings(chat_state.user_id)
    code_settings = collection_permissions.get_access_code_settings(access_code)

    # Determine the highest access role available
    role = max(
        code_settings.access_role,
        user_settings.access_role,
        cached_access_role,
        key=lambda x: x.value,
    )

    # Store the access role in chat_state for future use within the same session
    # We need this, because the access code is given only once, on load
    if role.value > cached_access_role.value:
        chat_state.set_cached_access_role(role, coll_name_full)

    ic(role)
    return role


def parse_shareable_link(link: str) -> tuple[str | None, str | None]:
    """
    Parse a shareable link to a collection and return the collection name and access code.
    """
    try:
        idx = link.index("?collection=") + 1  # start of "collection="
    except ValueError:
        return None, None

    parts = link[idx:].split("&")

    query_params = {}
    for part in parts:
        key_value = part.split("=")
        if len(key_value) != 2:
            return None, None
        query_params[key_value[0]] = key_value[1]

    collection_name = query_params.get("collection")
    access_code = query_params.get("access_code")
    return collection_name, access_code


def manage_dbs_console(chat_state: ChatState) -> Props:
    """
    Manage collections from the console (using `input`).
    NOTE: In console mode, there's no separation of users.
    """
    while True:
        # Print the menu and get the user's choice
        print()
        print(
            "WARNING: Console db management logic may be lagging behind the changes in "
            "the main code. Use with caution or consider switching to the Streamlit interface."
        )  # TODO
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
        else:
            print("This command is not available in console mode.")


def sort_collection_names(
    coll_names_as_shown: list[str], coll_names_full: list[str]
) -> tuple[list[str], list[str]]:
    # Sort the collections by name as shown, but put the default collection first
    coll_name_pairs = sorted(
        zip(coll_names_as_shown, coll_names_full),
        key=lambda pair: (pair[1] != DEFAULT_COLLECTION_NAME, pair[0]),
    )
    return tuple(zip(*coll_name_pairs))


BASE_DATETIME = datetime(2024, 5, 25, 0, 0, 0, tzinfo=timezone.utc)
COLLECTION_GROUP_SIZE = 20


def sort_collections(collections: list[Collection], user_id: str | None):
    # TODO: optimize
    def get_sort_key(collection: Collection):
        try:
            updated_at = parse_timestamp(collection.metadata["updated_at"])
        except (KeyError, TypeError):
            updated_at = BASE_DATETIME

        is_regular = (
            collection.name != DEFAULT_COLLECTION_NAME
        )  # put default coll first
        return (is_regular, -updated_at.timestamp(), collection.name)  # newest first

    # Sort the collections in reverse chronological order
    collections = sorted(collections, key=get_sort_key)
    # coll_groups = [
    #     collections[i : i + COLLECTION_GROUP_SIZE]
    #     for i in range(0, len(collections), COLLECTION_GROUP_SIZE)
    # ]
    # [get_user_facing_collection_name(user_id, n) for n in coll_names_full]
    return collections


def get_time_str(blah_at: str) -> str:
    return (
        parse_timestamp(blah_at).strftime(DB_CREATED_AT_TIMESTAMP_FORMAT)
        if blah_at
        else "before May 25, 2024"
    )


def get_available_collections_str(
    collections: list[Collection],
    user_id: str | None,
    idx_start: int,
    search_str: str | None = None,
) -> str:
    if search_str:
        if search_str.endswith("*"):
            search_str = search_str.rstrip("*")
            filter_func = lambda name: name.startswith(search_str)  # noqa
            if search_str:
                filter_str = f" that begin with `{search_str}`"
        else:
            filter_func = lambda name: search_str in name  # noqa
            filter_str = f" that contain `{search_str}`"
    else:
        filter_str = ""

    entries = []
    are_there_more = False
    start_idx_str = f" starting from number {idx_start + 1}" if idx_start else ""

    for i, collection in enumerate(collections[idx_start:], start=idx_start):
        if filter_str and not filter_func(collection.name):
            continue
        if len(entries) >= COLLECTION_GROUP_SIZE:
            are_there_more = True  # there are more matching collections than we'll show
            break  # break without adding the current collection

        dt = get_time_str((collection.metadata or {}).get("updated_at"))
        coll_name_as_shown = get_user_facing_collection_name(user_id, collection.name)
        entries.append(f"**{i+1}.** `{coll_name_as_shown}` - last updated {dt}")

    collections_str = "\n".join(entries)
    num_colls = len(collections)
    if not entries:
        return (
            f"No matching collections found. There are {num_colls} "
            "available collections in total."
        )

    res = f"There are {num_colls} available collections"
    if filter_str or start_idx_str:
        res += f". Collections{filter_str}{start_idx_str}"
    elif are_there_more:
        res += f". Showing collections 1-{len(entries)}"

    res += f":\n\n{collections_str}\n\n"

    if are_there_more:
        if filter_str:
            res += "Some older matching collections were not shown. "
            res += "Consider using a more specific search string. "
        else:
            new_start_num = idx_start + 1 + len(entries)
            res += f"To see older collections, use `/db list {new_start_num}+`. "
            res += "To narrow down the search, use `/db list <search string>`. "

    res += (
        "To switch to collection number N, type `/db use N`. To switch to a "
        "different collection you have access to, "
        "type `/db use <collection name or shareable link>`."
    )

    return res


def get_db_not_found_str(name: str, access_role: str = "owner") -> str:
    return (
        f"Collection `{name}` doesn't exist or you don't have {access_role} access to it. "
        f"Use `/db list` to see available collections or `/db` to see more options."
    ).replace("  ", " ")


def handle_db_status_command(chat_state: ChatState) -> Props:
    # Get the access role (refresh from db just in case)
    access_role = get_access_role(chat_state)

    # Form the answer
    coll_metadata = chat_state.vectorstore.get_cached_collection_metadata() or {}
    created_at = get_time_str(coll_metadata.get("created_at"))
    updated_at = get_time_str(coll_metadata.get("updated_at"))
    ans = (
        f"Full collection name: `{chat_state.vectorstore.name}`\n\n"
        f"Created: {created_at}\n\n"
        f"Last updated: {updated_at}\n\n"
        f"Your access role: {access_role.name.lower()}"
    )

    # If the user has owner access, show more details
    if access_role.value >= AccessRole.OWNER.value:
        # NOTE: this refetches the permissions, could be optimized
        collection_permissions = chat_state.get_collection_permissions()

        ans += "\n\nStored user access roles:"
        if not collection_permissions.user_id_to_settings:
            ans += "\n- No roles stored"
        for user_id, settings in collection_permissions.user_id_to_settings.items():
            ans += f"\n- User `{user_id}`: {settings.access_role.name.lower()}"

        ans += "\n\nStored access codes:"
        if not collection_permissions.access_code_to_settings:
            ans += "\n- No codes stored"
        for (
            code,
            settings,
        ) in collection_permissions.access_code_to_settings.items():
            ans += f"\n- Code `{code}`: {settings.access_role.name.lower()}"

    return format_nonstreaming_answer(ans)


def save_coll_data(chat_state: ChatState, collections: list[Collection]):
    coll_data = [c.name for c in collections]
    # for num, collection in enumerate(collections, start=1):
    #     coll_data.append(collection.name)

    chat_state.session_data["coll_data"] = coll_data


def handle_db_list_command(
    chat_state: ChatState, collections: list[Collection]
) -> Props:
    value = chat_state.parsed_query.message
    admin_pwd = BYPASS_SETTINGS_RESTRICTIONS_PASSWORD

    if value == admin_pwd:
        all_collections = chat_state.get_all_collections()
        all_coll_names_full = [c.name for c in all_collections]
        tmp = "\n".join([f"{i+1}. {n}" for i, n in enumerate(all_coll_names_full)])
        return format_nonstreaming_answer(
            f"Full collection names for all users:\n\n{tmp}"
        )

    # Check for commands such as '/db list 42+' and assign idx_start
    idx_start = 0
    if value.endswith("+"):
        try:
            idx_start = int(value[:-1]) - 1
            if idx_start < 0:
                idx_start = 0
            value = None
        except ValueError:
            pass

    save_coll_data(chat_state, collections)

    return format_nonstreaming_answer(
        get_available_collections_str(
            collections,
            user_id=chat_state.user_id,
            search_str=value,
            idx_start=idx_start,
        )
    )


def handle_db_use_command(
    chat_state: ChatState, collections: list[Collection]
) -> Props:
    value = chat_state.parsed_query.message

    if not value:
        return format_nonstreaming_answer(
            "To switch collections, you must provide the desired collection's "
            "name, its number in the list above, or a shareable link to it."
            "Example:\n```\n/db use 3\n```"
        )

    # Check if it's a shareable link
    coll_name_full, access_code = parse_shareable_link(value)
    if coll_name_full:
        # Handle '/db use <shareable link>'
        access_role = get_access_role(chat_state, coll_name_full, access_code)
        ic(access_role)
        if access_role.value < AccessRole.VIEWER.value:
            return format_nonstreaming_answer(
                get_db_not_found_str(coll_name_full, "viewer")
            )
        coll_name_to_show = coll_name_full
    else:
        # Not a link. Get the name of the collection to switch to
        try:
            # Construct hypothetical full collection name and try to find its index
            tmp = get_full_collection_name(chat_state.user_id, value)
            idx = next((i for i, c in enumerate(collections) if c.name == tmp))
            coll_name_to_show = value  # NOTE: can optimize above by using dict
            coll_name_full = tmp
        except StopIteration:  # collection not found by name
            try:
                # See if the user provided an index directly instead of a name
                idx = int(value) - 1
                if idx < 0 or idx >= len(collections):
                    raise ValueError
                coll_name_full = collections[idx].name
                coll_name_to_show = get_user_facing_collection_name(
                    chat_state.user_id, coll_name_full
                )
            except ValueError:
                # See if it's a non-native collection (shared with user)
                if get_access_role(chat_state, value).value <= AccessRole.NONE.value:
                    return format_nonstreaming_answer(get_db_not_found_str(value, ""))
                coll_name_to_show = coll_name_full = value

    vectorstore = chat_state.get_new_vectorstore(
        coll_name_full, create_if_not_exists=False
    )
    if vectorstore is None:
        return format_nonstreaming_answer(get_db_not_found_str(coll_name_to_show, ""))

    res = format_nonstreaming_answer(
        f"Switched to collection: `{coll_name_to_show}`."
    ) | {"vectorstore": vectorstore}

    if access_code:
        res["instructions"] = [
            Instruction(
                type=INSTRUCT_CACHE_ACCESS_CODE,
                user_id=chat_state.user_id,
                access_code=access_code,
            )
        ]

    return res


def handle_db_rename_command(chat_state: ChatState) -> Props:
    value = chat_state.parsed_query.message
    admin_pwd = BYPASS_SETTINGS_RESTRICTIONS_PASSWORD

    if not value:
        return format_nonstreaming_answer(
            "To rename the current collection, you must provide a new name. Example:\n"
            "```\n/db rename awesome-new-name\n```"
        )

    if chat_state.vectorstore.name == DEFAULT_COLLECTION_NAME:
        return format_nonstreaming_answer("You cannot rename the default collection.")

    # Admin can rename to the default collection's name by providing the password.
    # If it's not a special admin command, check if the user has owner access
    if value == f"--default {admin_pwd}" and admin_pwd:
        # Before renaming, we need to delete the default collection if it exists
        try:
            chat_state.vectorstore.delete_collection(DEFAULT_COLLECTION_NAME)
        except Exception:
            pass  # The default collection likely was deleted already
        value = DEFAULT_COLLECTION_NAME
    elif get_access_role(chat_state).value < AccessRole.OWNER.value:
        return format_nonstreaming_answer(
            "You can't rename the current collection because you "
            "don't have owner access to it."
        )

    # From this point on, the user has owner access to the collection

    # Get the full name of the collection to rename to
    main_owner_user_id = get_main_owner_user_id(chat_state.vectorstore.name)
    if value == DEFAULT_COLLECTION_NAME:
        # Will usually fail, but ok if admin has deleted the default collection
        new_full_name = DEFAULT_COLLECTION_NAME
    elif main_owner_user_id is None:
        # Public collection remains public
        new_full_name = value
        if new_full_name.startswith(PRIVATE_COLLECTION_PREFIX):
            return format_nonstreaming_answer(
                f"A public collection's name cannot start with `{PRIVATE_COLLECTION_PREFIX}`."
            )
    else:
        new_full_name = get_full_collection_name(chat_state.user_id, value)

    # Rename the collection
    try:
        chat_state.vectorstore.rename_collection(new_full_name)
    except Exception as e:
        return format_nonstreaming_answer(f"Error renaming collection: {e}")

    # Check if collection was taken away from the original owner and restore their access
    if main_owner_user_id != chat_state.user_id:
        chat_state.save_collection_settings_for_user(
            main_owner_user_id,
            CollectionUserSettings(access_role=AccessRole.OWNER),
        )
        print(f"Restored owner access to {main_owner_user_id}")

    # Get vectorstore with updated name, form and return the answer
    return format_nonstreaming_answer(f"Collection renamed to `{value}`.") | {
        "vectorstore": chat_state.get_new_vectorstore(new_full_name),
    }


def get_collection_nums(chat_state: ChatState):
    coll_data = chat_state.session_data.get("coll_data")
    return coll_data


def handle_db_delete_command(
    chat_state: ChatState, collections: list[Collection]
) -> Props:
    value = chat_state.parsed_query.message
    admin_pwd = BYPASS_SETTINGS_RESTRICTIONS_PASSWORD

    if not value:
        return format_nonstreaming_answer(
            "To delete a collection, you must provide the name of "
            "the collection to delete, a list of collection numbers, or "
            "the --current (-c) flag to delete the current collection. Examples:\n"
            "```\n/db delete my-temp-db\n/db delete 2, 4, 19\n"
            "/db delete 19\n/db delete -c\n```"
        )

    is_admin = False
    if admin_pwd and len(value.rsplit(maxsplit=1)) == 2:
        tmp, maybe_admin_pwd = value.rsplit(maxsplit=1)
        if maybe_admin_pwd == admin_pwd:
            is_admin = True
            value = tmp

    if value == "-c" or value == "--current":
        value = chat_state.vectorstore.name
    elif value == "-d" or value == "--default":
        value = DEFAULT_COLLECTION_NAME

    if value == DEFAULT_COLLECTION_NAME:
        if not is_admin:
            return format_nonstreaming_answer(
                "You cannot delete the default collection."
            )
        if chat_state.vectorstore.name == DEFAULT_COLLECTION_NAME:
            return format_nonstreaming_answer(
                "You cannot delete the default collection while it's in use."
            )

    # NOTE: The commented-out feature below requires allow_reset=True in the settings
    # or an ALLOW_RESET env variable **on the server**.
    # # Admin can also reset the whole db by providing the password
    # if value == f"--reset {pwd}" and pwd:
    #     chat_state.vectorstore.client.reset()
    #     return format_nonstreaming_answer("The entire database has been reset.")

    # Get the full name(s) of the collection(s) to delete
    try:
        # Construct hypothetical full collection name and try to find it
        tmp = get_full_collection_name(chat_state.user_id, value)
        next((None for c in collections if c.name == tmp))  # check if exists
        full_names = [tmp]
    # NOTE: there's a small chance of an ambiguity if the user has
    # a collection with the same name as a public collection, or if
    # they have their own collection with the as-shown name of
    # "u-<some other user's id>-<some other user's collection name>".
    # In both cases, the name will be resolved to the user's own collection.
    except StopIteration:  # collection not found by name
        try:
            # See if the user provided index(es) directly instead of a name
            # NOTE: this takes precedence over non-native collection name such as
            # "123" (which could be a public collection name), but that's ok, we don't
            # want to block the user from deleting a collection by its index and delete
            # a public collection by mistake.
            # NOTE: could prohibit collection names that are just numbers
            # NOTE: to mitigate the above, could allow quotes around the name ("42")
            if "-" in value:
                # Admin can delete a range of collections by providing the password
                if not is_admin:
                    raise ValueError
                leftright = value.split("-")
                if len(leftright) != 2:
                    raise ValueError
                min_idx, max_idx = int(leftright[0]) - 1, int(leftright[1]) - 1
                if (coll_data := get_collection_nums(chat_state)) is None:
                    return format_nonstreaming_answer(RUN_LIST_FIRST_MSG)
                if min_idx < 1 or max_idx >= len(coll_data) or min_idx > max_idx:
                    raise ValueError
                idxs = list(range(min_idx, max_idx + 1))
            else:
                # Usual case: see if we got a comma-separated list of indexes
                idxs = [int(s) - 1 for s in value.split(",")]

                if (coll_data := get_collection_nums(chat_state)) is None:
                    return format_nonstreaming_answer(RUN_LIST_FIRST_MSG)

                # Check that all idxs are valid
                if any(idx < 1 or idx >= len(coll_data) for idx in idxs):
                    raise ValueError  # idx == 0 not allowed, it's the default collection

            # One last check:
            if not idxs:
                raise ValueError

            # Get the full names of the collections
            full_names = [coll_data[idx] for idx in idxs]
        except ValueError:
            # It's a non-native collection (or bad input)
            full_names = [value]

    # Delete the collection(s)
    deleted_names_as_shown = []
    failed_names_as_shown = []
    error_msgs = []
    should_switch_to_default = False
    for full_name in full_names:
        name_as_shown = get_user_facing_collection_name(chat_state.user_id, full_name)
        try:
            if (
                not is_admin
                and get_access_role(chat_state, full_name).value
                < AccessRole.OWNER.value
            ):
                # NOTE: could have a separate NOT_EXIST "role" if we want to distinguish
                # between not found and not accessible even as a viewer
                raise ValueError("You don't have owner access to this collection.")

            chat_state.vectorstore.delete_collection(full_name)
            deleted_names_as_shown.append(name_as_shown)  # NOTE: could stream as we go

            # If the current collection was deleted, initiate a switch to the default collection
            if chat_state.collection_name == full_name:
                should_switch_to_default = True
        # NOTE: could stream progress here
        except Exception as e:
            # NOTE: will throw if someone deletes a collection that's being used
            failed_names_as_shown.append(name_as_shown)
            error_msgs.append(str(e))
            # error_msgs.append(format_exception(e))

    # Form answer
    s_or_no_s = "s" if len(deleted_names_as_shown) > 1 else ""
    ans = (
        f"Collection{s_or_no_s} `{', '.join(deleted_names_as_shown)}` deleted."
        if deleted_names_as_shown
        else ""
    )
    if failed_names_as_shown:
        s_or_no_s = "s" if len(failed_names_as_shown) > 1 else ""
        ans += (
            f"\n\nFailed to delete collection{s_or_no_s} `{', '.join(failed_names_as_shown)}`."
            f"\n\nError message{s_or_no_s}:\n"
        )
        for name, msg in zip(failed_names_as_shown, error_msgs):
            ans += f"\n- `{name}`: {msg}"

    ans = format_nonstreaming_answer(ans)

    # If the current collection was deleted, initiate a switch to the default collection
    if should_switch_to_default:
        ans["vectorstore"] = chat_state.get_new_vectorstore(DEFAULT_COLLECTION_NAME)

    return ans

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
    command = chat_state.parsed_query.db_command

    # Handle /db with no valid subcommand
    if command == DBCommand.NONE:
        if chat_state.operation_mode.value == OperationMode.CONSOLE.value:
            return manage_dbs_console(chat_state)
        else:
            return format_nonstreaming_answer(
                DB_COMMAND_HELP_TEMPLATE.format(current_db=chat_state.vectorstore.name)
            )

    # Handle the command
    collections = chat_state.get_user_collections()
    collections = sort_collections(collections, chat_state.user_id)  # need user_id?

    if command == DBCommand.STATUS:
        return handle_db_status_command(chat_state)
    if command == DBCommand.LIST:
        return handle_db_list_command(chat_state, collections)
    if command == DBCommand.USE:
        return handle_db_use_command(chat_state, collections)
    if command == DBCommand.RENAME:
        return handle_db_rename_command(chat_state)
    if command == DBCommand.DELETE:
        return handle_db_delete_command(chat_state, collections)
    # Should never happen
    raise ValueError(f"Invalid /db subcommand: {command}")
