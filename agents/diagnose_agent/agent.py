# agents/diagnose/agent.py
from agents.base import AgentResponse, IAgent
from .retriever import Retriever
from .generator import LLMGenerator

class DiagnosisAgent(IAgent):
    name = "diagnose"

    def __init__(self):
        self.retriever = Retriever()        # dùng Qdrant đã ingest
        self.llm = LLMGenerator()           # dùng model bạn đã config

    def answer(self, query: str) -> AgentResponse:
        docs = self.retriever.search(query, top_k=5, rerank_k=2)
        text_context = "\n\n".join(docs)
        final_text, rationale, model = self.llm.generate(query, text_context)

        return AgentResponse(
            task=self.name,
            answer=final_text,
            rationale=rationale,
            contexts=docs,
            meta={"model": model, "top_k": 5, "rerank_k": 2}
        )
