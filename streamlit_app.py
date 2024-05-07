import os

import streamlit as st
from icecream import ic  # noqa: F401

from _prepare_env import is_env_loaded
from agents.dbmanager import (
    get_access_role,
    get_short_user_id,
    get_user_facing_collection_name,
)
from components.llm import CallbackHandlerDDGStreamlit
from docdocgo import get_bot_response, get_source_links
from utils.chat_state import ChatState
from utils.helpers import (
    DELIMITER,
    EXAMPLE_QUERIES,
    GREETING_MESSAGE,
    GREETING_MESSAGE_PREFIX_DEFAULT,
    GREETING_MESSAGE_PREFIX_OTHER,
)
from utils.ingest import extract_text, format_ingest_failure
from utils.output import format_exception
from utils.prepare import (
    ALLOWED_MODELS,
    BYPASS_SETTINGS_RESTRICTIONS,
    BYPASS_SETTINGS_RESTRICTIONS_PASSWORD,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_OPENAI_API_KEY,
    INITIAL_TEST_QUERY_STREAMLIT,
    MODEL_NAME,
    TEMPERATURE,
    get_logger,
)
from utils.query_parsing import parse_query
from utils.streamlit.helpers import (
    STAND_BY_FOR_INGESTION_MESSAGE,
    DownloaderData,
    fix_markdown,
    just_chat_status_config,
    show_downloader,
    show_sources,
    show_uploader,
    status_config,
    write_slowly,
)
from utils.streamlit.ingest import ingest_docs
from utils.streamlit.prepare import prepare_app
from utils.strings import limit_number_of_characters
from utils.type_utils import (
    INSTRUCT_EXPORT_CHAT_HISTORY,
    AccessRole,
    ChatMode,
    chat_modes_needing_llm,
)

logger = get_logger()

# Page config
page_icon = "🦉"  # random.choice("🤖🦉🦜🦆🐦")
st.set_page_config(page_title="DocDocGo", page_icon=page_icon)
st.markdown(
    "<style>code {color: #8ACB88; overflow-wrap: break-word;}</style> ",
    unsafe_allow_html=True,
)

# Run just once
if "chat_state" not in st.session_state:
    prepare_app()
    # Need to reference is_env_loaded to avoid unused import being removed
    is_env_loaded = is_env_loaded  # more info at the end of docdocgo.py

chat_state: ChatState = st.session_state.chat_state

# Update the query params if scheduled on previous run
if st.session_state.update_query_params is not None:
    st.query_params.clear()  # NOTE: should be a way to set them in one go
    st.query_params.update(st.session_state.update_query_params)
    st.session_state.update_query_params = None

####### Sidebar #######
with st.sidebar:
    st.header("DocDocGo")

    with st.expander(
        "OpenAI API Key", expanded=not st.session_state.llm_api_key_ok_status
    ):
        supplied_openai_api_key = st.text_input(
            "OpenAI API Key",
            label_visibility="collapsed",
            key="openai_api_key",
            type="password",
        )

        if not supplied_openai_api_key:
            openai_api_key_to_use: str = st.session_state.default_openai_api_key
            is_community_key = not BYPASS_SETTINGS_RESTRICTIONS

        elif supplied_openai_api_key in ("public", "community"):
            # TODO: document this
            # This allows the user to use community key mode (and see public collections
            # even if BYPASS_SETTINGS_RESTRICTIONS is set
            openai_api_key_to_use: str = st.session_state.default_openai_api_key
            is_community_key = True

        elif supplied_openai_api_key == BYPASS_SETTINGS_RESTRICTIONS_PASSWORD:
            openai_api_key_to_use: str = st.session_state.default_openai_api_key
            is_community_key = False

            # Collapse key field (not super important, but nice)
            if not st.session_state.llm_api_key_ok_status:
                st.session_state.llm_api_key_ok_status = True  # collapse key field
                st.rerun()  # otherwise won't collapse until next interaction

        else:
            # Use the key entered by the user as the OpenAI API key
            openai_api_key_to_use: str = supplied_openai_api_key
            is_community_key = False

        # In case there's no community key available, set is_community_key to False
        if not openai_api_key_to_use:
            is_community_key = False
            st.caption("To use this app, you'll need an OpenAI API key.")
            "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
            chat_state.user_id = None
        elif is_community_key:
            st.caption(
                "Using the default OpenAI API key (some settings are restricted, "
                "your collections are public)."
            )
            "[Get your OpenAI API key](https://platform.openai.com/account/api-keys)"
            chat_state.user_id = None
        else:
            # User is using their own key (or has unlocked the default key)
            chat_state.user_id = get_short_user_id(openai_api_key_to_use)
            # TODO: use full api key as user id (but show only the short version)

        chat_state.is_community_key = is_community_key  # in case it changed

        # If user key field changed, reset user/vectorstore as needed
        if supplied_openai_api_key != st.session_state.prev_supplied_openai_api_key:
            is_initial_load = st.session_state.prev_supplied_openai_api_key is None
            st.session_state.prev_supplied_openai_api_key = supplied_openai_api_key
            chat_state.openai_api_key = openai_api_key_to_use

            # Determine which collection to use and whether user has access to it
            init_coll_name = (
                st.session_state.init_collection_name or chat_state.collection_name
            )
            access_role = get_access_role(
                chat_state, init_coll_name, st.session_state.access_code
            )
            is_authorised = access_role.value > AccessRole.NONE.value

            # Different logic depending on whether collection is supplied in URL or not
            if st.session_state.init_collection_name:
                if is_authorised:
                    chat_state.chat_history_all.append(
                        (
                            None,
                            f"Welcome! You are now using the `{init_coll_name}` collection. "
                            "When chatting, I will use its content as my knowledge base. "
                            "To get help using me, just type `/help <your question>`.",
                        )
                    )
                else:
                    chat_state.chat_history_all.append(
                        (
                            None,
                            "Apologies, the current URL doesn't provide access to the "
                            f"requested collection `{init_coll_name}`. This can happen if the "
                            "access code is invalid or if the collection doesn't exist.\n\n"
                            "I have switched to my default collection.\n\n"
                            "To get help using me, just type `/help <your question>`.",
                        )
                    )
                    init_coll_name = DEFAULT_COLLECTION_NAME
            elif not is_initial_load:
                # If no collection is supplied in the URL, use current or default collection
                should_add_msg_and_load_collection = True
                if is_authorised:
                    chat_state.chat_history_all.append(
                        (
                            None,
                            "Welcome! The user credentials have changed but you are still "
                            "authorised for the current collection.",
                        )
                    )
                else:
                    chat_state.chat_history_all.append(
                        (
                            None,
                            "Welcome! The user credentials have changed, "
                            "so I've switched to the default collection.",
                        )
                    )
                    init_coll_name = DEFAULT_COLLECTION_NAME

            # In either of the above cases, load the collection. The only case when we don't
            # need to (re-)load is if it's the initial run and there's no collection in the URL.
            if st.session_state.init_collection_name or not is_initial_load:
                # Switch to the new collection (or just reload the current one)
                chat_state.vectorstore = chat_state.get_new_vectorstore(init_coll_name)

                # Since we added a message, we must inc sources_history's length
                chat_state.sources_history.append(None)

    # Settings
    with st.expander("Settings", expanded=False):
        if is_community_key:
            model_options = [MODEL_NAME]  # only show 3.5 if community key
            index = 0
        else:
            model_options = ALLOWED_MODELS  # guaranteed to include MODEL_NAME
            index = model_options.index(chat_state.bot_settings.llm_model_name)
        # TODO: adjust context length (for now assume 16k)
        chat_state.bot_settings.llm_model_name = st.selectbox(
            "Language model", model_options, disabled=is_community_key, index=index
        )

        # Temperature
        chat_state.bot_settings.temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=2.0,
            value=TEMPERATURE,
            step=0.1,
            format="%f",
        )
        if chat_state.bot_settings.temperature >= 1.5:
            st.caption(":red[Very high temperatures can lead to **jibberish**]")
        elif chat_state.bot_settings.temperature >= 1.0:
            st.caption(":orange[Consider a lower temperature if precision is needed]")

    # Resources
    with st.expander("Resources", expanded=True):
        "[Command Cheatsheet](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md#using-docdocgo)"
        "[Full Docs](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md)"

####### Main page #######
if tmp := os.getenv("STREAMLIT_WARNING_NOTIFICATION"):
    st.warning(tmp)

if chat_state.collection_name == DEFAULT_COLLECTION_NAME:
    st.markdown(GREETING_MESSAGE + GREETING_MESSAGE_PREFIX_DEFAULT)
else:
    st.markdown(GREETING_MESSAGE + GREETING_MESSAGE_PREFIX_OTHER)

with st.expander("See a quick walkthrough"):
    st.markdown(EXAMPLE_QUERIES)
# NOTE: weirdly, if the following two lines are switched, a strange bug occurs
# with a ghostly but still clickable "Upload" button (or the Tip) appearing within the newest
# user message container, only as long as the AI response is being typed out
with st.expander("Want to upload your own documents?"):
    if st.session_state.idx_file_upload == -1:
        files, allow_all_ext = show_uploader(border=False)
    st.markdown(":grey[**Tip:** During chat, just say `/upload` to upload more docs!]")

# Show previous exchanges and sources
is_downloaded = False
for i, (msg_pair, sources) in enumerate(
    zip(chat_state.chat_history_all, chat_state.sources_history)
):
    full_query, answer = msg_pair
    if full_query is not None:
        with st.chat_message("user", avatar=st.session_state.user_avatar):
            st.markdown(fix_markdown(full_query))
    if answer is not None or sources is not None:
        with st.chat_message("assistant", avatar=st.session_state.bot_avatar):
            if answer is not None:
                st.empty()  # to "replace" status & fix ghost double text issue
                st.markdown(fix_markdown(answer))
            show_sources(sources)
    if i == st.session_state.idx_file_upload:
        files, allow_all_ext = show_uploader()  # there can be only one
    if i == st.session_state.idx_file_download:
        is_downloaded = show_downloader()  # there can be only one


# Check if the user has uploaded files
if files:
    # Ingest the files
    docs, failed_files, unsupported_ext_files = extract_text(files, allow_all_ext)

    # Display failed files, if any
    if failed_files or unsupported_ext_files:
        with st.chat_message("assistant", avatar=st.session_state.bot_avatar):
            tmp = format_ingest_failure(failed_files, unsupported_ext_files)
            if unsupported_ext_files:
                tmp += (
                    "\n\nIf your files with unsupported extensions can be treated as "
                    "text files, check the `Allow all extensions` box and try again."
                )
            st.markdown(fix_markdown(tmp))

    # Ingest the docs into the vectorstore, if any
    if docs:
        ingest_docs(docs, chat_state)

# Check if the user has entered a query
coll_name_full = chat_state.vectorstore.name
coll_name_as_shown = get_user_facing_collection_name(chat_state.user_id, coll_name_full)
full_query = st.chat_input(f"{limit_number_of_characters(coll_name_as_shown, 35)}/")
if not full_query:
    # If no message from the user, check if we should run an initial test query
    if not chat_state.chat_history_all and INITIAL_TEST_QUERY_STREAMLIT:
        full_query = INITIAL_TEST_QUERY_STREAMLIT

# Parse the query or get the next scheduled query, if any
if full_query:
    parsed_query = parse_query(full_query)
else:
    parsed_query = chat_state.scheduled_queries.pop()
    if not parsed_query:
        st.stop()  # nothing to do
    full_query = "AUTO-INSTRUCTION: Run scheduled query."
    try:
        num_iterations_left = parsed_query.research_params.num_iterations_left
        full_query += f" {num_iterations_left} research iterations left."
    except AttributeError:
        pass

#### The rest will only run once there is a parsed query to run ####
chat_mode = parsed_query.chat_mode
chat_state.update(parsed_query=parsed_query)
is_ingest_via_file_uploader = (
    chat_mode == ChatMode.INGEST_COMMAND_ID and not parsed_query.message
)

# Display the user message (or the auto-instruction)
if full_query:
    with st.chat_message("user", avatar=st.session_state.user_avatar):
        # NOTE: should use a different avatar for auto-instructions
        st.markdown(fix_markdown(full_query))

# Get and display response from the bot
with st.chat_message("assistant", avatar=st.session_state.bot_avatar):
    # Prepare status container and display initial status
    # TODO: statuses need to be updated to correspond with reality
    try:
        if is_ingest_via_file_uploader:
            raise KeyError  # to skip the status
        status = st.status(status_config[chat_mode]["thinking.header"])
        status.write(status_config[chat_mode]["thinking.body"])
    except KeyError:
        status = None

    # Prepare container and callback handler for showing streaming response
    message_placeholder = st.empty()

    cb = CallbackHandlerDDGStreamlit(
        message_placeholder,
        end_str=STAND_BY_FOR_INGESTION_MESSAGE
        if parsed_query.is_ingestion_needed()
        else "",
    )
    chat_state.callbacks[1] = cb
    chat_state.add_to_output = lambda x: cb.on_llm_new_token(x, run_id=None)
    try:
        response = get_bot_response(chat_state)
        answer = response["answer"]

        # Check if this is the first time we got a response from the LLM
        if (
            not st.session_state.llm_api_key_ok_status
            and chat_mode in chat_modes_needing_llm
        ):
            # Set a temp value to trigger a rerun to collapse the API key field
            st.session_state.llm_api_key_ok_status = "RERUN_PLEASE"

        # Display non-streaming responses slowly (in particular avoids chat prompt flicker)
        if chat_mode not in chat_modes_needing_llm or "needs_print" in response:
            write_slowly(message_placeholder, answer)

        # Display sources if present
        sources = get_source_links(response) or None  # Cheaper to store None than []
        show_sources(sources, cb)

        # Display the "complete" status - custom or default
        if status:
            default_status = status_config.get(chat_mode, just_chat_status_config)
            status.update(
                label=response.get("status.header", default_status["complete.header"]),
                state="complete",
            )
            status.write(response.get("status.body", default_status["complete.body"]))

        # Add the response to the chat history
        chat_state.chat_history.append((full_query, answer))

        # If the response contains instructions to auto-run a query, record it
        if new_parsed_query := response.get("new_parsed_query"):
            chat_state.scheduled_queries.add_to_front(new_parsed_query)
    except Exception as e:
        # Add the error message to the likely incomplete response
        err_msg = format_exception(e)
        answer = f"Apologies, an error has occurred:\n```\n{err_msg}\n```"

        # Display the "error" status
        if status:
            status.update(label=status_config[chat_mode]["error.header"], state="error")
            status.write(status_config[chat_mode]["error.body"])

        err_type = (
            "OPENAI_API_AUTH"
            if (
                err_msg.startswith("AuthenticationError")
                and "key at https://platform.openai" in err_msg
            )
            else "EMBEDDINGS_DIM"
            if err_msg.startswith("InvalidDimensionException")
            else "OTHER"
        )

        if err_type == "OPENAI_API_AUTH":
            if is_community_key:
                answer = f"Apologies, the community OpenAI API key ({st.session_state.default_openai_api_key[:4]}...{DEFAULT_OPENAI_API_KEY[-4:]}) was rejected by the OpenAI API. Possible reasons:\n- OpenAI believes that the key has leaked\n- The key has reached its usage limit\n\n**What to do:** Please get your own key at https://platform.openai.com/account/api-keys and enter it in the sidebar."
            elif openai_api_key_to_use:
                answer = f"Apologies, the OpenAI API key you entered ({openai_api_key_to_use[:4]}...) was rejected by the OpenAI API. Possible reasons:\n- The key is invalid\n- OpenAI believes that the key has leaked\n- The key has reached its usage limit\n\n**What to do:** Please get a new key at https://platform.openai.com/account/api-keys and enter it in the sidebar."
            else:
                answer = "In order to use DocDocGo, you'll need an OpenAI API key. Please get one at https://platform.openai.com/account/api-keys and enter it in the sidebar."

        elif err_type == "EMBEDDINGS_DIM":
            answer = (
                "Apologies, on Feb 10, 2024, my embeddings model has been upgraded to a new, "
                "more powerful model. It looks like your collection is still using the old model. "
                "If you need to recover your collection please contact my author, Dmitriy Vasilyuk, "
                "via the project's GitHub repository or through LinkedIn at "
                "https://www.linkedin.com/in/dmitriyvasilyuk/."
            )
        elif cb.buffer:
            answer = f"{cb.buffer}\n\n{answer}"

        # Assign sources
        sources = None

        # Display the response with the error message
        print(f"{answer}\n{DELIMITER}")
        message_placeholder.markdown(fix_markdown(answer))

        # Stop this run
        if os.getenv("RERAISE_EXCEPTIONS"):
            raise e
        st.stop()
    finally:
        # Update the full chat history and sources history
        chat_state.chat_history_all.append((full_query, answer))
        chat_state.sources_history.append(sources)

# Display the file uploader if needed
if is_ingest_via_file_uploader:
    st.session_state.idx_file_upload = len(chat_state.chat_history_all) - 1
    files, allow_all_ext = show_uploader(is_teleporting=True)

# Display the file downloader if needed
for instruction in response.get("instructions", []):
    if instruction.type == INSTRUCT_EXPORT_CHAT_HISTORY:
        st.session_state.idx_file_download = len(chat_state.chat_history_all) - 1
        is_downloaded = show_downloader(
            DownloaderData(data=instruction.data, file_name="chat-history.md"),
            is_teleporting=True,
        )

# Update vectorstore if needed
if "vectorstore" in response:
    chat_state.vectorstore = response["vectorstore"]

# Update the collection name in the address bar if collection has changed
if coll_name_full != chat_state.vectorstore.name:
    st.session_state.update_query_params = {"collection": chat_state.vectorstore.name}

# If this was the first LLM response, rerun to collapse the OpenAI API key field
if st.session_state.llm_api_key_ok_status == "RERUN_PLEASE":
    st.session_state.llm_api_key_ok_status = True
    st.rerun()

# If there are scheduled queries, rerun to run the next one
if chat_state.scheduled_queries:
    st.rerun()

# If user switched to a different collection, rerun to display new collection name
if coll_name_full != chat_state.vectorstore.name:
    st.rerun()
