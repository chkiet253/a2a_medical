import json, random
from datetime import datetime, timedelta
from typing import Any, AsyncIterable, Dict, Optional
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

def propose_slots(disease: str, preferred_date: Optional[str] = None, clinic: str = "General Clinic") -> dict[str, Any]:
    base = datetime.strptime(preferred_date, "%Y-%m-%d") if preferred_date else datetime.now()
    slots = []
    for i in range(5):
        d = (base + timedelta(days=random.randint(0, 30))).date().isoformat()
        period = random.choice(["AM", "PM"])
        slots.append({
            "slot_id": f"{d}-{period}",   # <- đổi thành slot_id
            "date": d,
            "note": f"{d} {period}",
            "clinic": clinic,
            "disease": disease
        })
    return {
        "disease": disease,
        "clinic": clinic,
        "available_slots": slots,         # <- available_slots
        "selected_slot_id": "",           # <- selected_slot_id
        "patient_name": ""                # <- patient_name
    }



def _return_form(form: dict[str, Any], tool_context: ToolContext, instructions: str = "") -> str:
    tool_context.actions.skip_summarization = True
    tool_context.actions.escalate = True
    schema = {
        "type": "object",
        "properties": {
            "disease": {"type": "string", "title": "Bệnh"},
            "clinic": {"type": "string", "title": "Khoa/Phòng khám"},
            "patient_name": {"type": "string", "title": "Tên bệnh nhân"},
            "selected_slot_id": {"type": "string", "title": "Mã lịch đã chọn"},
            "available_slots": {
                "type": "array",
                "title": "Các lịch khả dụng (chọn một bằng mã)",
                "items": {
                    "type": "object",
                    "properties": {
                        "slot_id": {"type": "string", "title": "Mã lịch"},
                        "date": {"type": "string", "title": "Ngày"},
                        "note": {"type": "string", "title": "Mô tả lịch"},
                        "clinic": {"type": "string", "title": "Khoa khám"},
                        "disease": {"type": "string", "title": "Bệnh"},
                    },
                    "required": ["slot_id", "date", "note"]
                }
            }
        },
        "required": ["disease", "clinic", "available_slots", "selected_slot_id", "patient_name"]
    }


    return json.dumps({
        "type": "form",
        "form": schema,
        "form_data": form,
        "instructions": instructions
    })

def book_slot(selected_slot_id: str, patient_name: str) -> dict[str, Any]:
    if not selected_slot_id or not patient_name:
        return {"status": "error", "message": "Missing selected_slot_id or patient_name"}
    return {
        "status": "confirmed",
        "confirmation_id": f"BK{random.randint(100000,999999)}",
        "selected_slot_id": selected_slot_id,
        "patient_name": patient_name
    }

def return_schedule_form(form: dict[str, Any], tool_context: ToolContext):
    return _return_form(
        form,
        tool_context,
        "Chọn một vị trí theo ID và điền tên của bạn. "
        "Bạn có thể thay đổi ngày bằng cách chỉnh sửa 'vị trí' hoặc gửi ngày mới mong muốn."
    )
class SchedulingAgent:
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

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
        session = await self._runner.session_service.get_session(app_name=self._agent.name, user_id=self._user_id, session_id=session_id)
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(app_name=self._agent.name, user_id=self._user_id, state={}, session_id=session_id)
        events = await self._runner.run_async(user_id=self._user_id, session_id=session.id, new_message=content)
        if not events or not events[-1].content or not events[-1].content.parts:
            return ""
        return "\n".join([p.text for p in events[-1].content.parts if p.text])

    async def stream(self, query, session_id) -> AsyncIterable[Dict[str, Any]]:
        session = await self._runner.session_service.get_session(app_name=self._agent.name, user_id=self._user_id, session_id=session_id)
        content = types.Content(role="user", parts=[types.Part.from_text(text=query)])
        if session is None:
            session = await self._runner.session_service.create_session(app_name=self._agent.name, user_id=self._user_id, state={}, session_id=session_id)
        async for event in self._runner.run_async(user_id=self._user_id, session_id=session.id, new_message=content):
            if event.is_final_response():
                response = ""
                if event.content and event.content.parts and event.content.parts[0].text:
                    response = "\n".join([p.text for p in event.content.parts if p.text])
                elif event.content and event.content.parts and any(p.function_response for p in event.content.parts):
                    response = next((p.function_response.model_dump() for p in event.content.parts))
                yield {"is_task_complete": True, "content": response}
            else:
                yield {"is_task_complete": False, "updates": "Proposing time slots..."}
    
    def _build_agent(self) -> LlmAgent:
        return LlmAgent(
            model="gemini-2.0-flash-001",
            name="de_xuat_va_dat_lich",
            description="Gợi ý lịch hẹn và đặt lịch hẹn với biểu mẫu có thể chỉnh sửa.",
            instruction="""
            Bạn lên lịch hẹn khám bệnh.
            Quy trình làm việc:
            1) Nếu người dùng nêu tên bệnh (và tùy chọn ngày ưu tiên), hãy gọi propose_slots(disease, preferred_date?).
            2) Ngay lập tức gọi return_schedule_form để hiển thị biểu mẫu có thể chỉnh sửa với danh sách 'available_slots', cùng 'selected_slot_id' và 'patient_name' để người dùng điền/chọn.
            3) Khi người dùng gửi biểu mẫu đã điền đầy đủ (có selected_slot_id + patient_name), hãy gọi book_slot(selected_slot_id, patient_name).
            4) Trả lời bằng một xác nhận đặt lịch ngắn gọn (status, confirmation_id).

            Nếu thiếu disease, hãy hỏi ngắn gọn về bệnh đó.
            """,

            tools=[propose_slots, return_schedule_form, book_slot],
        )
