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

from datetime import datetime

def propose_slots(disease: str, preferred_date: str, clinic: str) -> dict[str, Any]:
    base = datetime.strptime(preferred_date, "%Y-%m-%d") if preferred_date else datetime.now()
    slots = []
    for i in range(5):
        d = (base + timedelta(days=random.randint(0, 30))).date().isoformat()
        period = random.choice(["AM", "PM"])
        slots.append({
            "slot_id": f"{d}-{period}",
            "date": d,
            "note": f"{d} {period}",
            "clinic": clinic,
            "disease": disease
        })
    return {
        "disease": disease,
        "clinic": clinic,
        "available_slots": slots,
        "selected_slot_id": "",
        "patient_name": ""
    }


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
            instruction = """
            You are a scheduling tool for medical appointments.
            1) Always call default_schedule(disease, patient_name).
            2) If disease or patient_name is missing, pass an empty string "".
            3) Always return a fixed confirmation (status, confirmation_id, date, note).
            4) Do not ask the user any follow-up questions.
            """
            ,

            tools=[propose_slots],
        )
