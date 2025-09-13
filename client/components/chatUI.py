import streamlit as st
from utils.api import ask_question

def render_chat():
    st.subheader("💬 Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        st.chat_message(m["role"]).markdown(m["content"])

    q = st.chat_input("Nhập câu hỏi y khoa...")
    if not q: return
    st.session_state.messages.append({"role":"user","content":q})
    st.chat_message("user").markdown(q)

    resp = ask_question(q)
    if resp.status_code != 200:
        st.error(f"Server error {resp.status_code}: {resp.text}")
        return

    data = resp.json()
    answer = data.get("answer","")
    rationale = data.get("rationale","")
    meta = data.get("meta",{})
    contexts = data.get("contexts",[])

    md = f"**Kết quả:**\n\n{answer}\n\n—\n**Lý do:** {rationale}\n\n*Model:* `{meta.get('model','?')}`"
    st.chat_message("assistant").markdown(md)
    st.session_state.messages.append({"role":"assistant","content":md})

    if contexts:
        with st.expander("📄 Contexts"):
            for i, ctx in enumerate(contexts, 1):
                st.markdown(f"**[{i}]** {ctx}")