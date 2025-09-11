from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import json, os
from typing import List, Dict, Any, Iterable

class VectorDB:
    def __init__(self, url=None, api_key=None, collection=None, dim: int = 1024):
        self.url = url or os.getenv("QDRANT_URL")
        self.api_key = api_key or os.getenv("QDRANT_API_KEY")
        self.collection = collection or os.getenv("QDRANT_COLLECTION", "med_docs_m3")
        self.dim = dim
        self.client = QdrantClient(url=self.url, api_key=self.api_key)
        self.ensure_collection()

    def ensure_collection(self):
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE)
            )

    def _iter_jsonl(self, jsonl_path: str) -> Iterable[Dict[str, Any]]:
        with open(jsonl_path, "r", encoding="utf-8") as fr:
            for line in fr:
                if not line.strip():
                    continue
                yield json.loads(line)

    # ================== KHÔNG BATCH, ID ỔN ĐỊNH ==================
    def upsert_jsonl(self, jsonl_path: str, embedder, use_ws_if_available: bool = True) -> None:
        """
        Đọc JSONL (mỗi dòng: id, context, text_ws?) -> embed -> upsert 1 lần.

        Args:
            jsonl_path: đường dẫn file .jsonl
            embedder: instance EmbeddingGenerator (encode_texts(list[str]) -> np.ndarray [N, D])
            use_ws_if_available: True -> ưu tiên text_ws khi embed
        """
        records: List[Dict[str, Any]] = list(self._iter_jsonl(jsonl_path))
        if not records:
            return

        # 1) Chọn văn bản để embed
        texts: List[str] = [
            (r.get("text_ws") if (use_ws_if_available and r.get("text_ws")) else r.get("context", ""))
            for r in records
        ]

        # (tuỳ chọn) kiểm tra dữ liệu tối thiểu
        for i, r in enumerate(records):
            if "id" not in r:
                raise ValueError(f"Missing 'id' at line {i}")
            if "context" not in r and "text_ws" not in r:
                raise ValueError(f"Missing 'context'/'text_ws' at line {i}")

        # 2) Encode toàn bộ (BGE-M3; embedder đã L2-normalize)
        vecs = embedder.encode_texts(texts)  # np.ndarray [N, self.dim]

        # 3) Chuẩn bị points và upsert
        points = [
            PointStruct(
                id=str(records[i]["id"]),     # UUID string hợp lệ
                vector=vecs[i].tolist(),
                payload=records[i],           # giữ nguyên: id, context, text_ws?
            )
            for i in range(len(records))
        ]
        self.client.upsert(collection_name=self.collection, points=points)

    # ================== SEARCH ==================
    def search(self, query_vec, top_k: int = 5):
        return self.client.search(
            collection_name=self.collection,
            query_vector=query_vec.tolist(),
            limit=top_k
        )