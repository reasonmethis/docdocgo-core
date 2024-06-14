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
    GREETING_MESSAGE,
    GREETING_MESSAGE_SUFFIX_DEFAULT,
    GREETING_MESSAGE_SUFFIX_OTHER,
    VERSION,
    WALKTHROUGH_TEXT,
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
    get_init_msg,
    just_chat_status_config,
    mode_option_to_prefix,
    mode_options,
    show_downloader,
    show_sources,
    show_uploader,
    status_config,
    update_url_if_scheduled,
    write_slowly,
)
from utils.streamlit.ingest import ingest_docs
from utils.streamlit.prepare import prepare_app
from utils.strings import limit_num_characters
from utils.type_utils import (
    INSTRUCT_EXPORT_CHAT_HISTORY,
    AccessRole,
    ChatMode,
    chat_modes_needing_llm,
)

logger = get_logger()

# Page config
# page_icon = "🦉"  # random.choice("🤖🦉🦜🦆🐦")
st.logo(logo := "media/ddg-logo.png")
st.set_page_config(page_title="DocDocGo", page_icon=logo)
st.markdown(  # TODO: use lighter color if dark theme
    "<style>code {color: #005F26; overflow-wrap: break-word;  font-weight: 600; }</style> ",
    # "<style>code {color: #8ACB88; overflow-wrap: break-word;}</style> ",
    unsafe_allow_html=True,
)  # 005F26 (7.88:1 on lt, 7.02 on F0F2F6)
# text color for dark theme: e6e6e6

ss = st.session_state
if "chat_state" not in ss:
    # Run just once
    prepare_app()
    # Need to reference is_env_loaded to avoid unused import being removed
    is_env_loaded = is_env_loaded  # more info at the end of docdocgo.py

chat_state: ChatState = ss.chat_state

# Update the query params if scheduled on previous run
update_url_if_scheduled()

####### Sidebar #######
with st.sidebar:
    st.header("DocDocGo " + VERSION)

    with st.expander("OpenAI API Key", expanded=not ss.llm_api_key_ok_status):
        supplied_openai_api_key = st.text_input(
            "OpenAI API Key",
            label_visibility="collapsed",
            key="openai_api_key",
            type="password",
        )

        if not supplied_openai_api_key:
            openai_api_key_to_use: str = ss.default_openai_api_key
            is_community_key = not BYPASS_SETTINGS_RESTRICTIONS

        elif supplied_openai_api_key in ("public", "community"):
            # TODO: document this
            # This allows the user to use community key mode (and see public collections
            # even if BYPASS_SETTINGS_RESTRICTIONS is set
            openai_api_key_to_use: str = ss.default_openai_api_key
            is_community_key = True

        elif supplied_openai_api_key == BYPASS_SETTINGS_RESTRICTIONS_PASSWORD:
            openai_api_key_to_use: str = ss.default_openai_api_key
            is_community_key = False

            # Collapse key field (not super important, but nice)
            if not ss.llm_api_key_ok_status:
                ss.llm_api_key_ok_status = True  # collapse key field
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

        # If init load or user key field changed, reset user/vectorstore as needed
        if supplied_openai_api_key != ss.prev_supplied_openai_api_key:
            is_initial_load = ss.prev_supplied_openai_api_key is None
            ss.prev_supplied_openai_api_key = supplied_openai_api_key
            chat_state.openai_api_key = openai_api_key_to_use

            # Determine which collection to use and whether user has access to it
            coll_name_in_url = ss.init_collection_name
            init_coll_name = coll_name_in_url or chat_state.collection_name
            access_role = get_access_role(chat_state, init_coll_name, ss.access_code)
            is_authorised = access_role.value > AccessRole.NONE.value
            if is_authorised:
                if tmp := chat_state.get_new_vectorstore(
                    init_coll_name, create_if_not_exists=False
                ):
                    chat_state.vectorstore = tmp
                else:
                    # Due to optimizations collection may not exist despite is_authorised
                    is_authorised = False
            if not is_authorised:
                chat_state.vectorstore = chat_state.get_new_vectorstore(
                    DEFAULT_COLLECTION_NAME, create_if_not_exists=False
                )
                # Since we switched collections, we need to update the URL
                ss.update_query_params = {}  # schedule update
                logger.info(f"update_query_params: {ss.update_query_params}")

            init_msg = get_init_msg(
                is_initial_load, is_authorised, coll_name_in_url, init_coll_name
            )

            if init_msg:
                chat_state.chat_history_all.append((None, init_msg))
                chat_state.sources_history.append(None)

    # Default mode
    default_mode = st.selectbox("Default mode", mode_options, index=0)
    cmd_prefix = mode_option_to_prefix[default_mode]

    # Settings
    with st.expander("Settings", expanded=False):
        if is_community_key:
            model_options = [MODEL_NAME]  # show only 3.5 if community key
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
    st.markdown(GREETING_MESSAGE + GREETING_MESSAGE_SUFFIX_DEFAULT)
else:
    st.markdown(GREETING_MESSAGE + GREETING_MESSAGE_SUFFIX_OTHER)

with st.expander("See a quick walkthrough"):
    st.markdown(WALKTHROUGH_TEXT)
# NOTE: weirdly, if the following two lines are switched, a strange bug occurs
# with a ghostly but still clickable "Upload" button (or the Tip) appearing within the newest
# user message container, only as long as the AI response is being typed out
with st.expander("Want to chat with your own documents?"):
    if ss.idx_file_upload == -1:
        files, allow_all_ext = show_uploader(border=False)
    st.markdown(":grey[**Tip:** During chat, just say `/upload` to upload more docs!]")

# Show sample queries
clicked_sample_query = None
for _ in range(5):
    st.write("")
for i, (btn_col, sample_query) in enumerate(zip(st.columns(3), ss.sample_queries)):
    with btn_col:
        if st.button(sample_query, key=f"query{i}"):
            clicked_sample_query = sample_query

# Show previous exchanges and sources
is_downloaded = False
for i, (msg_pair, sources) in enumerate(
    zip(chat_state.chat_history_all, chat_state.sources_history)
):
    full_query, answer = msg_pair
    if full_query is not None:
        with st.chat_message("user", avatar=ss.user_avatar):
            st.markdown(fix_markdown(full_query))
    if answer is not None or sources is not None:
        with st.chat_message("assistant", avatar=ss.bot_avatar):
            if answer is not None:
                st.empty()  # to "replace" status & fix ghost double text issue
                st.markdown(fix_markdown(answer))
            show_sources(sources)
    if i == ss.idx_file_upload:
        files, allow_all_ext = show_uploader()  # there can be only one
    if i == ss.idx_file_download:
        is_downloaded = show_downloader()  # there can be only one


# Check if the user has uploaded files
if files:
    # Ingest the files
    docs, failed_files, unsupported_ext_files = extract_text(files, allow_all_ext)

    # Display failed files, if any
    if failed_files or unsupported_ext_files:
        with st.chat_message("assistant", avatar=ss.bot_avatar):
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
chat_input_text = f"[{default_mode}] " if cmd_prefix else ""
chat_input_text = limit_num_characters(chat_input_text + coll_name_as_shown, 40) + "/"
full_query = st.chat_input(chat_input_text)
if full_query:
    # Prepend the command prefix for the user-selected default mode, if needed
    if cmd_prefix and not full_query.startswith("/"):
        full_query = cmd_prefix + full_query
else:
    # If no message from the user, check if we should run an initial test query
    if not chat_state.chat_history_all and INITIAL_TEST_QUERY_STREAMLIT:
        full_query = INITIAL_TEST_QUERY_STREAMLIT
    elif clicked_sample_query:
        full_query = clicked_sample_query

# Parse the query or get the next scheduled query, if any
if full_query:
    parsed_query = parse_query(full_query)
else:
    parsed_query = chat_state.scheduled_queries.pop()
    if not parsed_query:
        if ss.update_query_params is not None:  # NOTE: hacky
            st.rerun()
        else:
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
    with st.chat_message("user", avatar=ss.user_avatar):
        # NOTE: should use a different avatar for auto-instructions
        st.markdown(fix_markdown(full_query))

# Get and display response from the bot
with st.chat_message("assistant", avatar=ss.bot_avatar):
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
        if not ss.llm_api_key_ok_status and chat_mode in chat_modes_needing_llm:
            # Set a temp value to trigger a rerun to collapse the API key field
            ss.llm_api_key_ok_status = "RERUN_PLEASE"

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
                answer = f"Apologies, the community OpenAI API key ({ss.default_openai_api_key[:4]}...{DEFAULT_OPENAI_API_KEY[-4:]}) was rejected by the OpenAI API. Possible reasons:\n- OpenAI believes that the key has leaked\n- The key has reached its usage limit\n\n**What to do:** Please get your own key at https://platform.openai.com/account/api-keys and enter it in the sidebar."
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
    ss.idx_file_upload = len(chat_state.chat_history_all) - 1
    files, allow_all_ext = show_uploader(is_teleporting=True)

# Display the file downloader if needed
for instruction in response.get("instructions", []):
    if instruction.type == INSTRUCT_EXPORT_CHAT_HISTORY:
        ss.idx_file_download = len(chat_state.chat_history_all) - 1
        is_downloaded = show_downloader(
            DownloaderData(data=instruction.data, file_name="chat-history.md"),
            is_teleporting=True,
        )

# Update vectorstore if needed
if "vectorstore" in response:
    chat_state.vectorstore = response["vectorstore"]

# Update the collection name in the address bar if collection has changed
if coll_name_full != chat_state.vectorstore.name:
    ss.update_query_params = (
        {"collection": chat_state.vectorstore.name}
        if chat_state.vectorstore.name != DEFAULT_COLLECTION_NAME
        else {}
    )

# If this was the first LLM response, rerun to collapse the OpenAI API key field
if ss.llm_api_key_ok_status == "RERUN_PLEASE":
    ss.llm_api_key_ok_status = True
    st.rerun()

# If user switched to a different collection, rerun to display new collection name
if ss.update_query_params is not None:
    st.rerun()

# If there are scheduled queries, rerun to run the next one
if chat_state.scheduled_queries:
    st.rerun()
