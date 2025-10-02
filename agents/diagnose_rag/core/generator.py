from __future__ import annotations
import os, requests, re
from typing import List, Dict, Any

SYSTEM_PROMPT = (
    "Bạn là bác sĩ chẩn đoán bệnh. "
    "NHIỆM VỤ: đưa ra MỘT chẩn đoán duy nhất dựa trên Context. "
    "Nếu không đủ dữ kiện, trả lời đúng chuỗi: 'Không đủ thông tin trong nguồn'."
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
        f"Context (trích dẫn đánh số):\n{ctx}\n\n"
        "BẮT BUỘC output đúng format:\n"
        "Chẩn đoán: <Tên bệnh>\n"
        "Lý do: <ngắn gọn, 1-3 câu có [1],[2] nếu phù hợp>\n"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user}
    ]


class LLMGenerator:
    """
    LLaMA-only generator.
    Provider chọn qua .env:
      - LLM_PROVIDER=openrouter -> meta-llama/Meta-Llama-3.1-8B-Instruct
      - LLM_PROVIDER=ollama     -> llama3.1:8b-instruct (local Ollama)
    """
    def __init__(self, temperature: float = 0.2, provider: str | None = None, **_):
        self.temperature = float(temperature)
        self.provider = (provider or os.getenv("LLM_PROVIDER", "openrouter")).lower()

        self.openrouter_base = os.getenv("OPENROUTER_BASE", "https://openrouter.ai/api/v1")
        self.ollama_base     = os.getenv("OLLAMA_BASE", "http://localhost:11434")
        self.openrouter_key  = os.getenv("OPENROUTER_API_KEY") or ""

        # Model API key từ .env
        self.model = os.getenv("LLM_MODEL")
        if not self.model:
            raise ValueError("Thiếu LLM_MODEL trong .env")


        if self.model is None:
            raise ValueError(f"LLM_PROVIDER không hỗ trợ: {self.provider}. Hãy dùng openrouter | ollama.")

    def chat(self, messages: List[Dict[str, str]]) -> str:
        if self.provider == "groq":
            groq_key = os.getenv("GROQ_API_KEY") or ""
            groq_base = os.getenv("GROQ_BASE", "https://api.groq.com/openai/v1")
            if not groq_key:
                raise RuntimeError("GROQ_API_KEY trống trong .env")
            r = requests.post(
                f"{groq_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                    "stream": False,
                },
                timeout=120,
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]


        if self.provider == "ollama":
            r = requests.post(
                f"{self.ollama_base}/api/chat",
                json={"model": self.model, "messages": messages,
                      "stream": False, "options": {"temperature": self.temperature}},
                timeout=120,
            )
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
                return data["message"].get("content", "")
            if "choices" in data and data["choices"]:
                return data["choices"][0]["message"]["content"]
            raise RuntimeError(f"Ollama response không mong đợi: {data}")

        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {self.provider}")


class DiagnosisAgent:
    def __init__(self, retriever, llm: LLMGenerator):
        self.retriever = retriever
        self.llm = llm

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        query = payload.get("query", "")
        if not query:
            return {"error": "Missing query"}
        return self.answer(query)

    def answer(self, query: str) -> Dict[str, Any]:
        hits = self.retriever(query)
        contexts = [h["text"] for h in hits]
        messages = build_prompt(query, contexts)
        txt = self.llm.chat(messages).strip()

        disease, rationale = None, None
        if "Không đủ thông tin trong nguồn" not in txt:
            for line in txt.splitlines():
                if re.match(r"(?i)^\s*chẩn đoán\s*:", line):
                    disease = line.split(":", 1)[-1].strip()
                elif re.match(r"(?i)^\s*lý do\s*:", line):
                    rationale = line.split(":", 1)[-1].strip()

            if not disease:
                disease = txt.split("\n", 1)[0].strip()
            if not rationale:
                rationale = "Không rõ lý do"

        return {
            "disease": disease,
            "rationale": rationale,
            "answer_raw": txt,
            "contexts": hits,
            "model": getattr(self.llm, "model", None),
        }
