from __future__ import annotations
from typing import List, Dict, Any
import torch
from sentence_transformers import CrossEncoder


class ViRanker:
    def __init__(self, model_name: str = "namdp-ptit/ViRanker"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CrossEncoder(model_name, device=device, model_kwargs={"use_safetensors": True})

    def rerank(self, query: str, docs: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
        if not docs:
            return []
        pairs = [[query, d["text"]] for d in docs]
        scores = self.model.predict(pairs)
        order = scores.argsort()[::-1][:top_k]
        out = []
        for idx in order:
            item = dict(docs[int(idx)])
            meta = dict(item.get("meta") or {})
            meta["ranker_score"] = float(scores[int(idx)])
            item["meta"] = meta
            out.append(item)
        return out


class Retriever:
    def __init__(self, vectordb, embedder, reranker: ViRanker | None = None,
                 top_k: int = 8, rerank_k: int = 3):
        self.db = vectordb
        self.embedder = embedder
        self.reranker = reranker
        self.top_k = top_k
        self.rerank_k = rerank_k

    def __call__(self, query: str) -> List[Dict[str, Any]]:
        qvec = self.embedder.encode_query([query])[0]
        hits = self.db.search(qvec, top_k=self.top_k)

        docs = []
        for h in hits:
            payload = h.payload or {}
            text_for_llm = payload.get("context") or payload.get("text_ws") or ""
            meta = {
                "id": payload.get("id"),
                "book_name": payload.get("book_name"),
                "page": payload.get("page"),
                "score": float(h.score),
                "ranker_score": None,
            }
            docs.append({"text": text_for_llm, "meta": meta})

        if self.reranker:
            return self.reranker.rerank(query, docs, top_k=min(self.rerank_k, len(docs)))
        return docs[: self.rerank_k]
