# diagnose/agent.py
from __future__ import annotations
from typing import AsyncIterator, Dict, Any, List, Optional
import asyncio

# Core components for diagnose agent
from core.embedder import EmbeddingGenerator
from core.vector_db import VectorDB
from core.retriever import Retriever, ViRanker
from core.generator import LLMGenerator, DiagnosisAgent

# class Agent:
#     SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

#     def __init__(self):
#         self.embedder = EmbeddingGenerator()
#         self.vector_db = VectorDB()
#         self.retriever = Retriever(self.vector_db, reranker=ViRanker())
#         self.generator = LLMGenerator()
#         self.core_agent = DiagnosisAgent(
#             embedder=self.embedder,
#             retriever=self.retriever,
#             generator=self.generator,
#         )

#     async def invoke(self, query, session_id) -> str:
#         return await self.core_agent.invoke(query, session_id)

#     async def stream(self, query, session_id):
#         async for event in self.core_agent.stream(query, session_id):
#             yield event

class Diagnose:
    """
    Diagnose Agent chạy trên chuẩn A2A/ADK:
    - RAG: Qdrant + BGE-M3 + ViRanker reranking.
    - LLM: Gemma2 (qua LLMGenerator) + format trả lời giàu căn cứ.
    - Streaming: luôn yield dict có 'is_task_complete'.
    """
    SUPPORTED_CONTENT_TYPES = ["text", "text/plain"]

    def __init__(
        self,
        top_k: int = 8,
        rerank_k: int = 3,
        use_ws_for_query: bool = True,
        temperature: float = 0.2,
    ) -> None:
        # 1) Embedding & Vector DB
        self.embedder = EmbeddingGenerator(use_vncorenlp=use_ws_for_query)
        self.vdb = VectorDB()

        # 2) Retriever: dense + cross-encoder rerank
        self.reranker = ViRanker()
        self.retriever = Retriever(
            vectordb=self.vdb,
            embedder=self.embedder,
            reranker=self.reranker,
            top_k=top_k,
            rerank_k=rerank_k,
        )

        # 3) LLM + logic chẩn đoán (ép format trong core.generator)
        self.llm = LLMGenerator(temperature=temperature)
        self.core = DiagnosisAgent(self.retriever, self.llm)

    # Non-stream, dùng cho _invoke khi client không subscribe
    def answer(self, query: str) -> Dict[str, Any]:
        return self.core.answer(query)

    async def invoke(self, query: str, session_id: Optional[str] = None) -> str:
        result = self.core.answer(query)
        return result.get("answer_raw", "")

    # Streaming theo ADK
    async def stream(
        self, query: str, session_id: Optional[str] = None
    ) -> AsyncIterator[Dict[str, Any]]:
        # Bước 1: thông báo tiến trình
        yield {"is_task_complete": False, "updates": "🔎 Đang truy vấn RAG..."}

        loop = asyncio.get_event_loop()

        # Bước 2: truy hồi ngữ cảnh (không block event-loop)
        hits: List[Dict[str, Any]] = await loop.run_in_executor(None, self.retriever, query)
        preview = []
        for h in hits:
            meta = h.get("meta", {}) or {}
            preview.append({
                "book_name": meta.get("book_name"),
                "page": meta.get("page"),
                "score": meta.get("score"),
                "ranker_score": meta.get("ranker_score"),
                "id": meta.get("id"),
            })
        yield {
            "is_task_complete": False,
            "updates": f"📚 Tìm thấy {len(hits)} đoạn liên quan.",
            "contexts_preview": preview,
        }

        # Bước 3: sinh câu trả lời cuối (core.generator)
        result: Dict[str, Any] = await loop.run_in_executor(None, self.core.answer, query)
        payload = {
            "answer": result.get("answer_raw"),
            "disease": result.get("disease"),
            "rationale": result.get("rationale"),
            "model": result.get("model"),
            "contexts": result.get("contexts"),
        }
        yield {"is_task_complete": True, "content": payload}
