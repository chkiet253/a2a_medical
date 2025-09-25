import json
import os
from typing import Any, AsyncIterable, Dict
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# ---- Load dữ liệu gói khám từ JSON ----
def _load_packages(filename: str = "goi_kham_vip_2025.json") -> dict:
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
    path = os.path.join(base_dir, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

_PACKAGES = _load_packages()["packages"]

# ---- Tool tính chi phí gói khám ----
def estimate_cost(name: str, gender: str) -> str:
    # Nếu thiếu gender, model vẫn có thể gửi ""
    if not gender:
        gender = "nam"

    for pkg in _PACKAGES:
        if pkg["name"].lower() == name.strip().lower():
            if isinstance(pkg["price"], dict):
                price = pkg["price"].get(gender, pkg["price"].get("nam", "N/A"))
            else:
                price = pkg["price"]
            return price
    return "Không tìm thấy gói khám"


# ---- Agent chính ----
class CostAgent:
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
                yield {"is_task_complete": False, "updates": "Đang tính toán chi phí gói khám..."}

    def _build_agent(self) -> LlmAgent:
        return LlmAgent(
            model="gemini-2.0-flash-001",
            name="agent_chi_phi",
            description="Trả về bảng chi phí và danh sách dịch vụ trong gói khám.",
            instruction = """
            You are a medical cost estimation tool for health checkup packages.
            1) Always call estimate_cost(name, gender).
            2) If gender is not provided by the user, pass an empty string "".
            3) Always return ONLY the cost (string in VND).
            4) If the package is not found, return 'Không tìm thấy gói khám'.
            """
            ,
            tools=[estimate_cost],
        )
