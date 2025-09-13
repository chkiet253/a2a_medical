
from typing import Dict, Any, Callable

class AgentCard:
    """Metadata + handler cho 1 agent"""
    def __init__(self, name: str, role: str, description: str,
                 handler: Callable[[Dict[str, Any]], Dict[str, Any]]):
        self.name = name
        self.role = role
        self.description = description
        self.handler = handler

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.handler(payload)