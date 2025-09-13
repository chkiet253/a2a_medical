from pydantic import BaseModel
from typing import List, Any, Dict

class AgentResponse(BaseModel):
    task: str                 # "diagnose" | "schedule" | ...
    answer: str               # câu trả lời chính (markdown-friendly)
    rationale: str | None = None
    contexts: List[str] = []  # top-k passages
    meta: Dict[str, Any] = {} # model, latency, top_k, vv.

class IAgent:
    name: str
    def answer(self, query: str) -> AgentResponse: ...
