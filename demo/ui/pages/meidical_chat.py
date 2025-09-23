# pages/medical_chat_demo.py
# Full demo: Chat + Form, dùng DiagnoseAgent thật, ReimbursementAgent thật, SchedulingAgent thật.
# Chạy: streamlit run pages/medical_chat_demo.py

import asyncio
import json
from datetime import date
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import streamlit as st
from hosts.multiagent.host_agent import HostAgent

# ====== Agent names ======
AGENT_REIMBURSEMENT_NAME = "Agent Chi Phí"
AGENT_SCHEDULING_NAME = "Agent Lịch Khám"

# ====== ToolContext stub ======
@dataclass
class _DummyActions:
    skip_summarization: bool = False
    escalate: bool = False

class _ToolContextStub:
    def __init__(self):
        self.state: Dict[str, Any] = {}
        self.actions = _DummyActions()
        self._artifacts: Dict[str, Any] = {}
    def save_artifact(self, file_id: str, file_part: Any):
        self._artifacts[file_id] = file_part

# ====== Init HostAgent ======
if "_host_impl" not in st.session_state:
    host = HostAgent([
        "http://localhost:10005",  # DiagnoseAgent
        "http://localhost:10002",  # ReimbursementAgent
        "http://localhost:10003",  # SchedulingAgent
    ]).create_agent()
    send_task_fn = None
    list_agents_fn = None
    for t in host.tools:
        if t.__name__ == "send_task":
            send_task_fn = t
        if t.__name__ == "list_remote_agents":
            list_agents_fn = t
    st.session_state._host_impl = send_task_fn.__self__
    st.session_state._list_agents = list_agents_fn

_host_impl: HostAgent = st.session_state._host_impl
_list_agents = st.session_state._list_agents

# ====== CSS font fix ======
st.set_page_config(page_title="Medical A2A Demo", page_icon="🩺")
st.markdown("""
<style>
html, body, [class*="css"], .stMarkdown, .stText, .stChatMessage {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial,
                 "Noto Sans", "Liberation Sans", "Apple Color Emoji", "Segoe UI Emoji",
                 "Segoe UI Symbol", "Noto Color Emoji" !important;
}
code, pre, .stCode, .stMarkdown code {
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Noto Sans Mono",
                 Consolas, monospace !important;
    font-variant-ligatures: none;
}
</style>
""", unsafe_allow_html=True)

# ====== Helpers ======
async def call_diagnose_agent(text_message: str) -> Tuple[List[Any], Dict[str, Any]]:
    tc = _ToolContextStub()
    parts = await _host_impl.send_task("diagnose_agent", text_message, tc)
    return parts, tc._artifacts

async def call_reimbursement_agent(disease_name: str) -> Dict[str, Any]:
    tc = _ToolContextStub()
    parts = await _host_impl.send_task(AGENT_REIMBURSEMENT_NAME, disease_name, tc)
    text_payload = "".join([p for p in parts if isinstance(p, str)])
    try:
        return json.loads(text_payload)
    except Exception:
        return {"raw": text_payload}

def render_reimbursement_result(info: Dict[str, Any]):
    st.markdown("### 💸 Chi phí (ReimbursementAgent)")
    st.json(info)

async def call_scheduling_agent(payload: Dict[str, Any]) -> Dict[str, Any]:
    tc = _ToolContextStub()
    msg = "SCHEDULE_REQUEST\n" + json.dumps(payload, ensure_ascii=False)
    parts = await _host_impl.send_task(AGENT_SCHEDULING_NAME, msg, tc)
    text_payload = "".join([p for p in parts if isinstance(p, str)])
    try:
        return json.loads(text_payload)
    except Exception:
        return {"raw": text_payload}

def render_schedule_result(info: Dict[str, Any]):
    st.markdown("### 🗓️ Lịch khám (SchedulingAgent)")
    st.json(info)

def stringify_parts(parts: List[Any]) -> str:
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        else:
            out.append(json.dumps(p, ensure_ascii=False))
    return "\n\n".join(out)

# ====== Sidebar ======
with st.sidebar:
    st.subheader("Agents từ Host")
    try:
        agents_list = _list_agents() if _list_agents else []
        for a in agents_list:
            st.write(f"• {a}")
    except Exception as e:
        st.warning(str(e))

# ====== Tabs ======
chat_tab, form_tab = st.tabs(["💬 Chat với Host", "🧾 Form nhanh"])

# ---------- Chat Tab ----------
with chat_tab:
    st.subheader("Chat với HostAgent")
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {"role": "assistant", "content": "Xin chào! Mình là Host trong hệ A2A Medical. Bạn có triệu chứng gì?"}
        ]
    for m in st.session_state.chat_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
    user_msg = st.chat_input("Nhập tin nhắn…")
    if user_msg:
        st.session_state.chat_messages.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)
        with st.chat_message("assistant"):
            with st.spinner("Đang gửi cho DiagnoseAgent…"):
                try:
                    payload = {"dialog": "user_symptoms_message", "text": user_msg}
                    msg_text = "DIAGNOSE_REQUEST\n" + json.dumps(payload, ensure_ascii=False, indent=2)
                    parts, artifacts = asyncio.run(call_diagnose_agent(msg_text))
                    diag_text = stringify_parts(parts)
                    st.markdown("### 🧠 Kết quả chẩn đoán")
                    st.markdown(diag_text)

                    with st.expander("💸 Ước tính chi phí (ReimbursementAgent)"):
                        disease = st.text_input("Tên bệnh", value="Cúm", key="chat_reimb")
                        if st.button("Tính chi phí", key="chat_reimb_btn"):
                            info = asyncio.run(call_reimbursement_agent(disease))
                            render_reimbursement_result(info)

                    with st.expander("🗓️ Đề xuất lịch khám (SchedulingAgent)"):
                        pname = st.text_input("Tên bệnh nhân", value="Nguyễn Văn A", key="chat_sched_name")
                        city = st.text_input("Thành phố", value="TP.HCM", key="chat_sched_city")
                        date_pref = st.date_input("Ngày mong muốn", key="chat_sched_date")
                        time_pref = st.selectbox("Khung giờ", ["Sáng","Chiều","Tối"], key="chat_sched_time")
                        if st.button("Đề xuất lịch", key="chat_sched_btn"):
                            sched_payload = {"patient": pname, "city": city, "date": str(date_pref), "time_pref": time_pref}
                            sched_info = asyncio.run(call_scheduling_agent(sched_payload))
                            render_schedule_result(sched_info)

                    st.session_state.chat_messages.append({"role": "assistant", "content": diag_text})
                except Exception as e:
                    err = f"Lỗi DiagnoseAgent: {e}"
                    st.error(err)
                    st.session_state.chat_messages.append({"role": "assistant", "content": err})

# ---------- Form Tab ----------
with form_tab:
    st.subheader("Form gửi DiagnoseAgent")
    name = st.text_input("Tên", value="Nguyễn Văn A")
    age = st.number_input("Tuổi", 0, 120, 30)
    gender = st.selectbox("Giới tính", ["Nam","Nữ","Khác"])
    symptoms = st.text_area("Triệu chứng")
    send = st.button("Gửi")
    if send:
        payload = {"user_name": name, "age": age, "gender": gender, "symptoms": symptoms}
        msg_text = "DIAGNOSE_REQUEST\n" + json.dumps(payload, ensure_ascii=False, indent=2)
        with st.spinner("Đang gửi cho DiagnoseAgent…"):
            try:
                parts, artifacts = asyncio.run(call_diagnose_agent(msg_text))
                diag_text = stringify_parts(parts)
                st.markdown("### 🧠 Kết quả chẩn đoán")
                st.markdown(diag_text)

                with st.expander("💸 Ước tính chi phí (ReimbursementAgent)"):
                    disease = st.text_input("Tên bệnh", value="Cúm", key="form_reimb")
                    if st.button("Tính chi phí", key="form_reimb_btn"):
                        info = asyncio.run(call_reimbursement_agent(disease))
                        render_reimbursement_result(info)

                with st.expander("🗓️ Đề xuất lịch khám (SchedulingAgent)"):
                    city = st.text_input("Thành phố", value="TP.HCM", key="form_sched_city")
                    date_pref = st.date_input("Ngày mong muốn", key="form_sched_date")
                    time_pref = st.selectbox("Khung giờ", ["Sáng","Chiều","Tối"], key="form_sched_time")
                    if st.button("Đề xuất lịch", key="form_sched_btn"):
                        sched_payload = {"patient": name, "city": city, "date": str(date_pref), "time_pref": time_pref}
                        sched_info = asyncio.run(call_scheduling_agent(sched_payload))
                        render_schedule_result(sched_info)
            except Exception as e:
                st.error(f"Lỗi DiagnoseAgent: {e}")
