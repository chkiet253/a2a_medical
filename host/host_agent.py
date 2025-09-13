from typing import Dict
from agents.base import IAgent, AgentResponse
from agents.diagnose_agent import DiagnosisAgent

class Host:
    def __init__(self):
        self.registry: Dict[str, IAgent] = {
            "diagnose": DiagnosisAgent()
        }

    def route(self, query: str) -> AgentResponse:
        # Router tối thiểu: mọi query → diagnose
        # (sau này thay bằng intent classifier để chọn agent)
        return self.registry["diagnose"].answer(query)

_host = None
def get_host() -> Host:
    global _host
    if _host is None:
        _host = Host()
    return _host