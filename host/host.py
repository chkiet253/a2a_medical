import os
from typing import Dict, Any
from common.agent_card import AgentCard
from diagnose_agent.generator import DiagnosisAgent

class Host:
    def __init__(self):
        self.registry = {}
        self._register_agents()

    def _register_agents(self):
        diagnose_agent = DiagnosisAgent()
        diagnose_card = AgentCard(
            name="diagnose",
            role="Diagnosis Agent",
            description="Phân tích triệu chứng, gợi ý chuyên khoa",
            handler=diagnose_agent.handle
        )
        self.registry["diagnose"] = diagnose_card

    def route(self, intent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if intent not in self.registry:
            return {"error": f"No agent found for intent: {intent}"}
        card = self.registry[intent]
        print(f"[Host] Routing to {card.name} ({card.role})")
        return card.run(payload)
