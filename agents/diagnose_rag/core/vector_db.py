from __future__ import annotations
import os
from qdrant_client import QdrantClient

class VectorDB:
    def __init__(self):
        self.url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.api_key = os.getenv("QDRANT_API_KEY", "")
        self.collection = os.getenv("QDRANT_COLLECTION", "med_docs_m3")
        self.client = QdrantClient(url=self.url, api_key=self.api_key)

    def search(self, query_vec, top_k: int = 8):
        return self.client.search(
            collection_name=self.collection,
            query_vector=query_vec.tolist(),
            limit=top_k
        )
