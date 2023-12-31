import os

import streamlit as st

from _prepare_env import is_env_loaded
from agents.dbmanager import (
    get_user_facing_collection_name,
    is_user_authorized_for_collection,
)
from components.llm import CallbackHandlerDDGStreamlit
from docdocgo import get_bot_response, get_source_links
from utils.chat_state import ChatState
from utils.helpers import DELIMITER, extract_chat_mode_from_query, parse_query
from utils.output import format_exception
from utils.prepare import DEFAULT_COLLECTION_NAME, TEMPERATURE
from utils.streamlit.helpers import show_sources, status_config, write_slowly
from utils.streamlit.prepare import prepare_app
from utils.strings import limit_number_of_characters
from utils.type_utils import chat_modes_needing_llm

# Run just once
if "chat_state" not in st.session_state:
    prepare_app()
    is_env_loaded = is_env_loaded  # see explanation at the end of docdocgo.py

chat_state: ChatState = st.session_state.chat_state

# Page config
page_icon = "🦉"  # random.choice("🤖🦉🦜🦆🐦")
st.set_page_config(page_title="DocDocGo", page_icon=page_icon)
st.title("DocDocGo")

# Sidebar
with st.sidebar:
    # Set the env variable for the OpenAI API key.
    # Init value of text field is determined by the init value of the env variable.
    with st.expander(
        "OpenAI API Key", expanded=not st.session_state.llm_api_key_ok_status
    ):
        user_openai_api_key = st.text_input(
            "OpenAI API Key",
            label_visibility="collapsed",
            key="openai_api_key",
            type="password",
        )

        # If the user has entered a non-empty OpenAI API key, use it
        if user_openai_api_key:
            # If a non-empty correct unlock pwd was entered, keep using the
            # default key but unlock the full settings
            if user_openai_api_key == os.getenv(
                "BYPASS_SETTINGS_RESTRICTIONS_PASSWORD"
            ):
                user_openai_api_key = ""
                if not st.session_state.allow_all_settings_for_default_key:
                    st.session_state.allow_all_settings_for_default_key = True
                    st.session_state.llm_api_key_ok_status = True  # collapse key field
                    st.rerun()  # otherwise won't collapse until next interaction
            else:
                # Otherwise, use the key entered by the user as the OpenAI API key
                openai_api_key_to_use = user_openai_api_key

        # If the user has not entered a key (or entered the unlock pwd) use the default
        if not user_openai_api_key:
            openai_api_key_to_use = st.session_state.default_openai_api_key
        is_community_key = (
            openai_api_key_to_use
            and not user_openai_api_key
            and not st.session_state.allow_all_settings_for_default_key
        )
        if is_community_key:
            st.caption(
                "Using the default OpenAI API key (some settings are restricted, "
                "your collections are public)."
            )
            "[Get your OpenAI API key](https://platform.openai.com/account/api-keys)"
            chat_state.user_id = None
        elif not openai_api_key_to_use:
            st.caption("To use this app, you'll need an OpenAI API key.")
            "[Get an OpenAI API key](https://platform.openai.com/account/api-keys)"
            chat_state.user_id = None
        else:
            # User is using their own key (or has unlocked the default key)
            chat_state.user_id = openai_api_key_to_use # use the key as the user id

        # If user (i.e. OpenAI API key) changed, reload the vectorstore
        is_auth = is_user_authorized_for_collection(
            chat_state.user_id, chat_state.vectorstore.name
        )
        if openai_api_key_to_use != chat_state.openai_api_key or not is_auth:
            # NOTE: the second condition is needed because the user could have
            # entered the unlock pwd and is now a "private" user, without a key change
            chat_state.openai_api_key = openai_api_key_to_use

            chat_state.vectorstore = chat_state.get_new_vectorstore(
                chat_state.vectorstore.name if is_auth else DEFAULT_COLLECTION_NAME,
            )
            chat_state.chat_and_command_history.append(
                (
                    None,
                    "I see that the user key has changed. Good to see you!"
                    if is_auth
                    else "The user has changed, so I switched to the default collection. Welcome!",
                )
            )
            chat_state.sources_history.append(None)  # keep the lengths in sync

    # Settings
    with st.expander("Settings", expanded=False):
        model_options = ["gpt-3.5-turbo-1106", "gpt-4-1106-preview"]
        if is_community_key:
            model_options = model_options[:1]
        # TODO: adjust context length (for now assume 16k)
        chat_state.bot_settings.llm_model_name = st.selectbox(
            "Language model", model_options, disabled=is_community_key
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
        "[Command Cheatsheet](https://github.com/reasonmethis/docdocgo-core/blob/main/docs/command-cheatsheet.md)"
        "[Full Docs](https://github.com/reasonmethis/docdocgo-core/blob/main/README.md)"

# If no message has been entered yet, show the intro
if not chat_state.chat_and_command_history:
    welcome_placeholder = st.empty()
    with welcome_placeholder.container():
        for i in range(3):
            st.write("")
        st.write("Welcome! To see what I can do, type")
        st.subheader("/help")
        st.write("")
        st.caption(
            ":red[⮟]:grey[ Tip: See your current **doc collection** in the chat box]"
        )

# Show previous exchanges and sources
for msg_pair, sources in zip(
    chat_state.chat_and_command_history, chat_state.sources_history
):
    full_query, answer = msg_pair
    if full_query is not None:
        with st.chat_message("user"):
            st.markdown(full_query)
    if answer is not None or sources is not None:
        with st.chat_message("assistant"):
            st.markdown(answer)
            show_sources(sources)

# Check if the user has entered a query
coll_name_full = chat_state.vectorstore.name
coll_name_as_shown = get_user_facing_collection_name(coll_name_full)
full_query = st.chat_input(f"{limit_number_of_characters(coll_name_as_shown, 35)}/")
if not (full_query):
    # If no message from the user, check if we should run an initial test query
    if not chat_state.chat_and_command_history and os.getenv(
        "INITIAL_TEST_QUERY_STREAMLIT"
    ):
        full_query = os.getenv("INITIAL_TEST_QUERY_STREAMLIT")
    else:
        st.stop()

#### The rest will only run once the user has entered a query ####

# Display the user's query
with st.chat_message("user"):
    st.markdown(full_query)
    # Remove the intro message if this is the first query
    if not chat_state.chat_and_command_history:
        welcome_placeholder.empty()

# Parse the query to extract command id & search params, if any
adjusted_full_query = "/help" if full_query.strip().lower() == "help" else full_query
query, chat_mode = extract_chat_mode_from_query(adjusted_full_query)
query, search_params = parse_query(query)
chat_state.update(chat_mode=chat_mode, message=query, search_params=search_params)

# Get and display response from the bot
with st.chat_message("assistant"):
    # Prepare status container and display initial status
    try:
        status = st.status(status_config[chat_mode]["thinking.header"])
        status.write(status_config[chat_mode]["thinking.body"])
    except KeyError:
        status = None

    # Prepare container and callback handler for showing streaming response
    message_placeholder = st.empty()
    callback_handler = CallbackHandlerDDGStreamlit(message_placeholder)
    chat_state.callbacks[1] = callback_handler
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
        if chat_mode not in chat_modes_needing_llm:
            write_slowly(message_placeholder, answer)

        # Display sources if present
        sources = get_source_links(response) or None  # Cheaper to store None than []
        show_sources(sources)

        # Display the "complete" status
        if status:
            status.update(
                label=status_config[chat_mode]["complete.header"], state="complete"
            )
            status.write(status_config[chat_mode]["complete.body"])

        # Add the response to the chat history if needed
        if not response.get("skip_chat_history", False):
            chat_state.chat_history.append((query, answer))
    except Exception as e:
        # Display the "error" status
        if status:
            status.update(label=status_config[chat_mode]["error.header"], state="error")
            status.write(status_config[chat_mode]["error.body"])

        # Add the error message to the likely incomplete response
        err_msg = format_exception(e)
        answer = f"Apologies, an error has occurred:\n```\n{err_msg}\n```"

        is_openai_api_key_error = (
            err_msg.startswith("AuthenticationError")
            and "key at https://platform.openai" in err_msg
        )

        if is_openai_api_key_error:
            if is_community_key:
                answer = f"Apologies, the community OpenAI API key ({st.session_state.default_openai_api_key[:4]}...{os.getenv('DEFAULT_OPENAI_API_KEY', '')[-4:]}) was rejected by the OpenAI API. Possible reasons:\n- OpenAI believes that the key has leaked\n- The key has reached its usage limit\n\n**What to do:** Please get your own key at https://platform.openai.com/account/api-keys and enter it in the sidebar."
            elif openai_api_key_to_use:
                answer = f"Apologies, the OpenAI API key you entered ({openai_api_key_to_use[:4]}...) was rejected by the OpenAI API. Possible reasons:\n- The key is invalid\n- OpenAI believes that the key has leaked\n- The key has reached its usage limit\n\n**What to do:** Please get a new key at https://platform.openai.com/account/api-keys and enter it in the sidebar."
            else:
                answer = "In order to use DocDocGo, you'll need an OpenAI API key. Please get one at https://platform.openai.com/account/api-keys and enter it in the sidebar."

        elif callback_handler.buffer:
            answer = f"{callback_handler.buffer}\n\n{answer}"

        # Assign sources
        sources = None

        # Display the response with the error message
        print(f"{answer}\n{DELIMITER}")
        message_placeholder.markdown(answer)

        # Stop this run
        if os.getenv("RERAISE_EXCEPTIONS"):
            raise e
        st.stop()
    finally:
        # Update the full chat history and sources history
        chat_state.chat_and_command_history.append((full_query, answer))
        chat_state.sources_history.append(sources)

# Update vectorstore if needed
if "vectorstore" in response:
    chat_state.vectorstore = response["vectorstore"]

# If this was the first exchange, rerun to remove the intro messages
if len(chat_state.chat_and_command_history) == 1:
    st.rerun()

# If this was the first LLM response, rerun to collapse the OpenAI API key field
if st.session_state.llm_api_key_ok_status == "RERUN_PLEASE":
    st.session_state.llm_api_key_ok_status = True
    st.rerun()

# If the user has switched to a different db, rerun to display the new db name
if coll_name_full != chat_state.vectorstore.name:
    st.rerun()
