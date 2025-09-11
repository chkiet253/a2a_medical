# retriever.py
from __future__ import annotations
from typing import List, Tuple, Dict, Any
import numpy as np
import torch
from sentence_transformers import CrossEncoder

class ViRanker:
    """
    Reranker dùng namdp-ptit/ViRanker (cross-encoder).
    Input: query + list passages
    Output: list[(idx, score)] sắp xếp giảm dần theo độ liên quan
    """
    def __init__(self, model_name: str = "namdp-ptit/ViRanker"):
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = CrossEncoder(
            model_name,
            device=device,
            automodel_args={"use_safetensors": True}
        )

    def rerank(self, query: str, passages: List[str], top_k: int = 2) -> List[Tuple[int, float]]:
        if not passages:
            return []
        pairs = [[query, p] for p in passages]
        scores = self.model.predict(pairs)  # np.ndarray [N]
        order = np.argsort(scores)[::-1][:top_k]
        return [(int(i), float(scores[i])) for i in order]


class Retriever:
    """
    Dense retrieval bằng Qdrant + BGE-M3 (EmbeddingGenerator) + ViRanker.
    - vectordb: có .search(qvec, top_k) -> hits (hit.payload, hit.score)
    - embedder: EmbeddingGenerator; KHUYẾN NGHỊ bật VNCoreNLP=True CHO QUERY để đồng bộ với index (text_ws)
    - reranker: ViRanker (hoặc None)
    """
    def __init__(self, vectordb, embedder, reranker: ViRanker | None = None,
                 top_k: int = 5, rerank_k: int = 2):
        self.db = vectordb
        self.embedder = embedder
        self.reranker = reranker
        self.top_k = top_k
        self.rerank_k = rerank_k

    def __call__(self, query: str) -> List[Dict[str, Any]]:
        # 1) Encode query (đồng bộ WS: embedder cho QUERY nên bật use_vncorenlp=True)
        qvec = self.embedder.encode_texts([query])[0]

        # 2) Vector search @Qdrant
        hits = self.db.search(qvec, top_k=self.top_k)

        # 3) Chuẩn bị passages (dùng context để LLM đọc tốt) + meta
        passages: List[str] = []
        metas: List[Dict[str, Any]] = []
        for h in hits:
            payload = h.payload or {}
            text_for_llm = payload.get("context") or payload.get("text_ws") or ""

            passages.append(text_for_llm)
            metas.append({
                "id": payload.get("id"),
                "book_name": payload.get("book_name"),
                "page": payload.get("page"),
                "used_for_embedding": payload.get("used_for_embedding"),
                "test_ws": payload.get("test_ws"),
                "score": h.score,          # cosine score từ Qdrant
            })

        # 4) Rerank nếu có; trả top 'rerank_k'
        if self.reranker and passages:
            order = self.reranker.rerank(query, passages, top_k=min(self.rerank_k, len(passages)))
            out = []
            for idx, s in order:
                meta = dict(metas[idx])
                meta["ranker_score"] = s
                out.append({
                    "text": passages[idx],
                    "meta": meta
                })
            return out

        # Không có reranker → trả theo Qdrant
        cut = min(self.rerank_k, len(passages))
        out = []
        for i in range(cut):
            meta = dict(metas[i])
            meta["ranker_score"] = None
            out.append({"text": passages[i], "meta": meta})
        return out
