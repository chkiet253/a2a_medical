import os
import torch
from FlagEmbedding import BGEM3FlagModel

class EmbeddingGenerator:
    def __init__(self, device: str | None = None, use_fp16: bool | None = None, use_vncorenlp: bool | None = None):
        # Decide device explicitly
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device

        if use_fp16 is None:
            use_fp16 = (self.device == "cuda")

        self.model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=use_fp16)
        # Try to move underlying torch model to target device (best effort; library may handle it internally)
        try:
            self.model.model.to(self.device)  # type: ignore[attr-defined]
        except Exception:
            pass

        if use_vncorenlp is None:
            use_vncorenlp = os.getenv("USE_VNCORENLP", "false").lower() == "true"
        self.use_vncorenlp = use_vncorenlp
        self._vnseg = None

    def _maybe_tokenize(self, texts: list[str]) -> list[str]:
        if not self.use_vncorenlp:
            return texts
        if self._vnseg is None:
            import vncorenlp
            # Yêu cầu: đã có model jar/thư mục 'vncorenlp'
            self._vnseg = vncorenlp.VnCoreNLP("vncorenlp", annotators=["wseg"])
        out = []
        for t in texts:
            sents = self._vnseg.word_segment(t)
            out.append(" ".join(" ".join(s) for s in sents))
        return out

    def encode_texts(self, texts: list[str], batch_size: int = 32, normalize: bool = True):
        texts = self._maybe_tokenize(texts)
        with torch.inference_mode():
            res = self.model.encode(
                texts,
                batch_size=batch_size,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False
            )
        vecs = res["dense_vecs"]
        if normalize:
            import numpy as np
            vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
        return vecs


    def device_info(self) -> dict:
        info = {
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "device": self.device,
        }
        if torch.cuda.is_available():
            try:
                info["cuda_device_name"] = torch.cuda.get_device_name(0)
            except Exception:
                info["cuda_device_name"] = None
        return info
