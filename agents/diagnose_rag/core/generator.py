from __future__ import annotations
import os, requests
from typing import List, Dict, Any

# Prompt builder (RAG VN)
SYSTEM_PROMPT = (
    "Bạn là bác sĩ chuẩn đoán. NHIỆM VỤ: đưa ra MỘT chẩn đoán duy nhất dựa trên Context. "
    "Không bịa. Nếu không đủ dữ kiện, trả lời: 'Không đủ thông tin trong nguồn'."
)

def build_prompt(user_q: str, contexts: list[str]) -> list[dict]:
    MAX_CHARS = 1400
    blocks = []
    for i, c in enumerate(contexts, 1):
        c = (c or "").strip().replace("\n", " ")
        if len(c) > MAX_CHARS:
            c = c[:MAX_CHARS] + "…"
        blocks.append(f"[{i}]\n{c}")
    ctx = "\n\n".join(blocks) if blocks else "(không có)"

    user = (
        f"Triệu chứng/câu hỏi: {user_q}\n\n"
        #f"Context (trích dẫn đánh số):\n{ctx}\n\n"
        "YÊU CẦU:\n"
        "- Chỉ dùng thông tin trong Context.\n"
        "- Trả lời duy nhất MỘT chẩn đoán dưới dạng:\n"
        "  Chẩn đoán: <Tên bệnh>\n"
        "  Lý do: <ngắn gọn, 1-3 câu có [1],[2] nếu phù hợp>\n"
        "- Nếu không đủ dữ kiện: trả lời đúng y chuỗi 'Không đủ thông tin trong nguồn'."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user}
    ]

# LLM
class LLMGenerator:
    """
    Chỉ dùng Gemma, chọn backend theo .env:
      - LLM_PROVIDER=groq       -> gemma2-9b-it (Groq)
      - LLM_PROVIDER=openrouter -> google/gemma-2-9b-it:free (OpenRouter)
      - LLM_PROVIDER=ollama     -> gemma2:9b-instruct (Ollama)
    Bạn có thể override base qua .env nếu cần, nhưng KHÔNG cần chỉ định model nữa.
    """
    def __init__(self, temperature: float = 0.2, provider: str | None = None, **_):
        self.temperature = float(temperature)
        self.provider = (provider or os.getenv("LLM_PROVIDER", "groq")).lower()

        # bases & keys
        self.groq_base        = os.getenv("GROQ_BASE", "https://api.groq.com/openai/v1")
        self.openrouter_base  = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
        self.ollama_base      = os.getenv("OLLAMA_BASE", "http://localhost:11434")
        self.groq_key         = os.getenv("GROQ_API_KEY") or ""
        self.openrouter_key   = os.getenv("OPENROUTER_API_KEY") or ""

        # GEMMA cố định theo provider
        self.model = {
            "groq":       "gemma2-9b-it",
            "openrouter": "google/gemma-2-9b-it:free",
            "ollama":     "gemma2:9b-instruct",
        }.get(self.provider)

        if self.model is None:
            raise ValueError(f"LLM_PROVIDER không hỗ trợ: {self.provider}. Hãy dùng groq | openrouter | ollama.")

    def chat(self, messages: List[Dict[str, str]]) -> str:
        if self.provider == "groq":
            if not self.groq_key:
                raise RuntimeError("GROQ_API_KEY trống trong .env")
            r = requests.post(
                f"{self.groq_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "temperature": self.temperature, "stream": False},
                timeout=120
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

        if self.provider == "openrouter":
            if not self.openrouter_key:
                raise RuntimeError("OPENROUTER_API_KEY trống trong .env")
            r = requests.post(
                f"{self.openrouter_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.openrouter_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages,
                      "temperature": self.temperature, "stream": False},
                timeout=120
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]

        if self.provider == "ollama":
            r = requests.post(
                f"{self.ollama_base}/api/chat",
                json={"model": self.model, "messages": messages,
                      "stream": False, "options": {"temperature": self.temperature}},
                timeout=120
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", "")
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            raise RuntimeError(f"Ollama response không mong đợi: {data}")

        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {self.provider}")

# Agent (RAG answer)
class DiagnosisAgent:
    """
    Chẩn đoán duy nhất 1 bệnh:
    - retriever(query) -> contexts (top sau ViRanker)
    - build_prompt(query, contexts) -> ép format
    - llm.chat(messages) -> Gemma (qua LLMGenerator)
    - parse kết quả thành {disease, rationale, answer_raw, contexts, model}
    """
    def __init__(self, retriever, llm):
        self.retriever = retriever
        self.llm = llm

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """API-style: nhận payload {query: "..."}"""
        query = payload.get("query", "")
        if not query:
            return {"error": "Missing query"}
        return self.answer(query)

    def answer(self, query: str) -> Dict[str, Any]:
        """Chẩn đoán từ câu hỏi query"""
        hits = self.retriever(query)  # [{"text","meta"}, ...]
        contexts = [h["text"] for h in hits]
        messages = build_prompt(query, contexts)
        txt = self.llm.chat(messages).strip()

        # Parse kết quả
        disease, rationale = None, None
        if "Không đủ thông tin trong nguồn" not in txt:
            for line in txt.splitlines():
                line = line.strip()
                if line.lower().startswith("chẩn đoán:"):
                    disease = line.split(":", 1)[-1].strip()
                elif line.lower().startswith("lý do:"):
                    rationale = line.split(":", 1)[-1].strip()
            if not disease:  # fallback
                disease = txt.split("\n", 1)[0].strip()

        return {
            "disease": disease,
            "rationale": rationale,
            "answer_raw": txt,
            "contexts": hits,
            "model": getattr(self.llm, "model", None),
        }
