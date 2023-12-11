import streamlit as st
from docdocgo import do_intro_tasks

st.title("DocDocGo")

# Run just once
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
    st.session_state.ws_data = None
    st.session_state.vectorstore = do_intro_tasks()

for query, answer in st.session_state.chat_history:
    with st.chat_message("user"):
        st.markdown(query)
    with st.chat_message("assistant"):
        st.markdown(answer)

if query := st.chat_input("What's on your mind?"):
    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        answer = ""
        for response in "1234567890":
            answer += response
            message_placeholder.markdown(answer + "▌")
        message_placeholder.markdown(answer)
    st.session_state.chat_history.append((query, answer))
