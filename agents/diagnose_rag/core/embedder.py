from __future__ import annotations
import unicodedata
from typing import List
import os
import torch
from FlagEmbedding import BGEM3FlagModel

# wrapper Java tự viết
from .vncorenlp_wrapper import VnCoreNLP  

def find_project_root(start_path: str, target_dir: str = "models"):
    """Leo lên các thư mục cha cho tới khi gặp folder target_dir."""
    cur = os.path.abspath(start_path)
    while True:
        candidate = os.path.join(cur, target_dir)
        if os.path.isdir(candidate):
            return cur
        new_cur = os.path.dirname(cur)
        if new_cur == cur:
            raise FileNotFoundError(f"Không tìm thấy thư mục {target_dir} từ {start_path}")
        cur = new_cur

class EmbeddingGenerator:
    def __init__(self, use_vncorenlp: bool = False) -> None:
        # 1) Load BGE-M3 embedding model
        device = "cuda" if torch.cuda.is_available() else "cpu"
        use_fp16 = device == "cuda"
        self.model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=use_fp16)

        # 2) Optionally load VNCoreNLP for word segmentation
        self.ws = None
        if use_vncorenlp:
            # Path tới root project
            BASE_DIR = find_project_root(__file__, "models")
            VNCORENLP_DIR = os.path.join(BASE_DIR, "models", "vncorenlp")
            if not os.path.exists(VNCORENLP_DIR):
                raise FileNotFoundError(f"Không tìm thấy thư mục VnCoreNLP: {VNCORENLP_DIR}")

            self.ws = VnCoreNLP(
                save_dir=VNCORENLP_DIR,
                annotators=["wseg"]
            )

    @staticmethod
    def _normalize(text: str) -> str:
        """Chuẩn hoá Unicode NFC + xoá khoảng trắng thừa"""
        return " ".join(unicodedata.normalize("NFC", text or "").split())

    def encode_query(self, texts: List[str], batch_size: int = 32):
        # 1) Normalize
        normed = [self._normalize(t) for t in texts]

        # 2) Word segmentation nếu có
        if self.ws:
            segs = []
            for t in normed:
                words = self.ws.word_segment(t)  # list[str]
                segs.append(" ".join(words))
            ws_texts = segs
        else:
            ws_texts = normed

        # 3) Encode bằng BGE-M3
        with torch.inference_mode():
            res = self.model.encode(
                ws_texts,
                batch_size=batch_size,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
        return res["dense_vecs"]
