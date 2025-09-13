import streamlit as st
from utils.api import ask_question

def render_chat():
    st.subheader("💬 Chat with your assistant")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).markdown(msg["content"])

    user_input = st.chat_input("Type your question....")
    if not user_input:
        return

    st.chat_message("user").markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    resp = ask_question(user_input)  # JSON by default
    try:
        if resp.status_code == 200:
            data = resp.json()
            answer = data.get("response", "")
            sources = data.get("sources", [])
            st.chat_message("assistant").markdown(answer)
            if sources:
                with st.expander("📄 Sources"):
                    for src in sources:
                        st.markdown(f"- `{src}`")
            st.session_state.messages.append({"role": "assistant", "content": answer})
        else:
            st.error(f"Error {resp.status_code}: {getattr(resp,'text','')}")
    except Exception as e:
        st.error(f"Client parsing error: {e}")
