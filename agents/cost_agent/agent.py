import json
from typing import Any, AsyncIterable, Dict
from google.adk.agents.llm_agent import LlmAgent
from google.adk.tools.tool_context import ToolContext
from google.adk.artifacts import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# ---- Helper để trả form ----
# def _return_form(form: dict[str, Any], tool_context: ToolContext, instructions: str = "") -> str:
#     tool_context.actions.skip_summarization = True
#     tool_context.actions.escalate = True
#     schema = {
#         "type": "object",
#         "properties": {
#             "benh": {"type": "string", "title": "Bệnh"},
#             "chi_phi": {"type": "string", "title": "Chi phí (VND)"},
#             "tong": {"type": "string", "title": "Tổng cộng (VND)"}
#         },
#         "required": ["benh", "chi_phi", "tong"]
#     }
#     return json.dumps({
#         "type": "form",
#         "form": schema,
#         "form_data": form,
#         "instructions": instructions
#     })

# ---- Bảng giá mẫu ----
_PRICE_TABLE = {
    "tiểu đường": 750000,
    "cao huyết áp": 450000,
    "cúm": 250000,
}

# ---- Tool tính chi phí ----
def estimate_cost(disease: str) -> dict[str, Any]:
    key = disease.strip().lower()
    total = _PRICE_TABLE.get(key, 100000)  # mặc định 100k
    return {
        "benh": disease,
        "chi_phi": str(total),
        "tong": str(total)
    }

# ---- Tool trả form ----
# def return_cost_form(form: dict, tool_context: ToolContext):
#     return _return_form(form, tool_context, "Bạn có thể điều chỉnh chi phí trước khi xác nhận.")

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
                yield {"is_task_complete": False, "updates": "Estimating medical costs..."}

    def _build_agent(self) -> LlmAgent:
        return LlmAgent(
            model="gemini-2.0-flash-001",
            name="agent_chi_phi",
            description="Trả về bảng chi phí y tế đơn giản cho một bệnh.",
            instruction="""
    Bạn là công cụ ước tính chi phí y tế.
    1) Nếu người dùng cung cấp tên bệnh (ví dụ: 'cúm', 'tiểu đường'),
    hãy gọi hàm estimate_cost(benh).
    2) Luôn trả về kết quả trực tiếp (dict có benh, chi_phi, tong).
    3) Không cần biểu mẫu chỉnh sửa.
    4) Nếu thiếu tên bệnh thì hãy hỏi lại ngắn gọn.
            """,
            tools=[estimate_cost],
        )

