import os
from typing import Any, AsyncIterable, Dict
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import các hàm nghiệp vụ
from db import find_available_doctors, get_available_slots, format_slots_human_readable
from helpers import get_all_doctors, send_email, write_confirm_email_v2, write_cancel_email_v2
from email_settings import from_email_default, password_default

# ---- Tool functions ----
def list_doctors() -> list[dict]:
    """Trả về danh sách bác sĩ và phòng khám"""
    return get_all_doctors()

def check_availability(date: str, time: str) -> list[dict]:
    """Tìm tất cả bác sĩ rảnh trong 30 phút tại date/time"""
    return find_available_doctors(date, time)

def show_slots(doctor_id: str, date: str) -> str:
    """Trả về slot còn trống của 1 bác sĩ trong ngày"""
    slots = get_available_slots(doctor_id, date)
    return format_slots_human_readable(slots)

def confirm_booking(patient_email: str, booking_data: dict) -> str:
    """Gửi mail xác nhận booking"""
    subject, body = write_confirm_email_v2(booking_data)
    send_email(patient_email, from_email_default, password_default, subject, body)
    return f"✅ Booking confirmed, email sent to {patient_email}"

def cancel_booking(patient_email: str, booking_data: dict) -> str:
    """Gửi mail hủy booking"""
    subject, body = write_cancel_email_v2(booking_data)
    send_email(patient_email, from_email_default, password_default, subject, body)
    return f"❌ Booking canceled, email sent to {patient_email}"


# ---- BookingAgent ----
class BookingAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "data", "form"]

    def __init__(self):
        self._agent = self._build_agent()
        self._user_id = "remote_agent"
        self._runner = Runner(
            app_name=self._agent.name,
            agent=self._agent,
            artifact_service=InMemoryArtifactService(),
            session_service=InMemorySessionService(),
            memory_service=InMemoryMemoryService(),
        )

    async def invoke(self, query, session_id) -> str:
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name, user_id=self._user_id, session_id=session_id
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name, user_id=self._user_id, state={}, session_id=session_id
            )
        events = await self._runner.run_async(user_id=self._user_id, session_id=session.id, new_message=content)
        if not events or not events[-1].content or not events[-1].content.parts:
            return ""
        return "\n".join([p.text for p in events[-1].content.parts if p.text])

    async def stream(self, query, session_id) -> AsyncIterable[Dict[str, Any]]:
        session = await self._runner.session_service.get_session(
            app_name=self._agent.name, user_id=self._user_id, session_id=session_id
        )
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(
                app_name=self._agent.name, user_id=self._user_id, state={}, session_id=session_id
            )
        async for event in self._runner.run_async(user_id=self._user_id, session_id=session.id, new_message=content):
            if event.is_final_response():
                response = ""
                if event.content and event.content.parts and event.content.parts[0].text:
                    response = "\n".join([p.text for p in event.content.parts if p.text])
                elif event.content and event.content.parts and any(p.function_response for p in event.content.parts):
                    response = next((p.function_response.model_dump() for p in event.content.parts))
                yield {"is_task_complete": True, "content": response}
            else:
                yield {"is_task_complete": False, "updates": "Đang xử lý yêu cầu đặt lịch khám..."}

    def _build_agent(self) -> LlmAgent:
        return LlmAgent(
            model="gemini-2.0-flash-001",
            name="agent_booking",
            description="Agent đặt lịch khám, kiểm tra lịch trống và gửi email xác nhận/hủy.",
            instruction = """
            Bạn là công cụ đặt lịch khám bệnh.
            - Nếu người dùng chưa cung cấp đủ thông tin (Họ tên, Ngày, Giờ, Email), hãy trả về text bắt đầu bằng "MISSING_INFO".
            - Nếu đủ thông tin thì gọi confirm_booking(...) hoặc cancel_booking(...).
            - Dùng list_doctors() để lấy danh sách bác sĩ.
            - Dùng check_availability(date, time) để tìm bác sĩ rảnh.
            - Dùng show_slots(doctor_id, date) để xem slot trống.
            - Dùng confirm_booking(patient_email, booking_data) để gửi email xác nhận.
            - Dùng cancel_booking(patient_email, booking_data) để gửi email hủy.
            Chỉ trả về text ngắn gọn, dễ hiểu.
            """
            ,
            tools=[list_doctors, check_availability, show_slots, confirm_booking, cancel_booking],
        )
