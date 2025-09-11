# -*- coding: utf-8 -*-
from __future__ import annotations
import os, json, re, unicodedata, time
from pathlib import Path
from collections import OrderedDict
from typing import List, Dict
from dotenv import load_dotenv
import math, time as _time
load_dotenv()

# Project deps (existing)
from a2a_medical.vector_db import VectorDB
from a2a_medical.embedder import EmbeddingGenerator
from a2a_medical.retriever import Retriever, ViRanker
from a2a_medical.generator import LLMGenerator, DiagnosisAgent

# ================= Utils =================
def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\sÀ-ỹ]", "", s)
    return s

def exact_match(pred: str, gold: str) -> int:
    return int(_normalize(pred) == _normalize(gold))

def bert_f1_vi(pred: str, gold: str) -> float:
    try:
        from bert_score import score as bertscore_score
        try:
            _, _, F1 = bertscore_score([pred],[gold], model_type="xlm-roberta-large", rescale_with_baseline=True)
        except Exception:
            _, _, F1 = bertscore_score([pred],[gold], model_type="xlm-roberta-large", rescale_with_baseline=False)
        return float(F1[0].item())
    except Exception:
        return 0.0

# ---- BGE-M3 helpers (1 instance dùng chung) ----
_BGE = None
def _bge():
    global _BGE
    if _BGE is None:
        from FlagEmbedding import BGEM3FlagModel
        _BGE = BGEM3FlagModel(os.getenv("TOKENIZER_MODEL","BAAI/bge-m3"), use_fp16=False)
    return _BGE

def cosine_similarity_bge(a: str, b: str) -> float:
    import numpy as np
    model = _bge()
    va = model.encode([a], return_dense=True)["dense_vecs"][0]
    vb = model.encode([b], return_dense=True)["dense_vecs"][0]
    va = va / (np.linalg.norm(va)+1e-12); vb = vb / (np.linalg.norm(vb)+1e-12)
    return float((va*vb).sum())

def wrong_format_check(text: str) -> int:
    t = (text or "").lower()
    if "không đủ thông tin trong nguồn" in t:
        return 0
    return int(not ("chẩn đoán:" in t and "lý do:" in t))

def extract_disease_from_answer(text: str) -> str:
    # Ưu tiên dòng "Chẩn đoán:"
    for line in (text or "").splitlines():
        if line.strip().lower().startswith("chẩn đoán:"):
            val = line.split(":", 1)[-1].strip()
            parts = [p.strip() for p in val.split(";") if p.strip()]
            return parts[-1] if parts else val
    # Không có → lấy phần cuối sau dấu ';' (hợp ví dụ "MCI; Bệnh Alzheimer")
    raw = (text or "").strip()
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    return parts[-1] if parts else raw

# ================= Prompt builder =================
SYSTEM_PROMPT = (
    "Bạn là bác sĩ hỗ trợ chẩn đoán ban đầu. Chỉ trả lời dựa trên Context. "
    "Nếu thông tin không đủ, hãy nói 'Không đủ thông tin trong nguồn'. "
    "Định dạng:\nChẩn đoán: <một bệnh duy nhất>\nLý do: <vắn tắt>."
)
def build_diag_prompt(user_q: str, contexts: List[str]):
    MAX = 1400
    blocks = []
    for i, c in enumerate(contexts, 1):
        t = (c or "").replace("\n", " ").strip()
        if len(t) > MAX: t = t[:MAX] + "…"
        blocks.append(f"[Đoạn {i}]\n{t}")
    ctx = "\n\n".join(blocks) if blocks else "(không có)"
    user = (f"Câu hỏi: {user_q}\n\nContext:\n{ctx}\n\nYêu cầu:\n"
            "- Chỉ dùng thông tin trong Context; không bịa.\n"
            "- Trả lời đúng định dạng đã nêu.")
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user}]

# ================= Helpers =================
def make_unique_per_disease(input_path: str, output_path: str) -> int:
    """Mỗi bệnh lấy 1 câu hỏi đầu tiên (ổn định)"""
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    first = OrderedDict()
    for item in data:
        d = (item.get("Disease") or "").strip()
        if not d or d in first:
            continue
        q = (item.get("Question") or "").strip()
        if q:
            first[d] = q
    uniq = [{"Disease": d, "Question": q} for d, q in first.items()]
    Path(output_path).write_text(json.dumps(uniq, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(uniq)

def write_jsonl(path: str, rows: list[dict]) -> str:
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fw:
        for r in rows:
            fw.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p.as_posix()

# ---------- Tokens & Triad helpers ----------
def _extract_usage_from_resp(resp_obj, llm_obj=None):
    in_tok = out_tok = None
    resp_text = None
    if isinstance(resp_obj, dict):
        usage = resp_obj.get("usage") or {}
        in_tok = usage.get("prompt_tokens") or usage.get("input_tokens")
        out_tok = usage.get("completion_tokens") or usage.get("output_tokens")
        resp_text = (resp_obj.get("text") or resp_obj.get("content") or resp_obj.get("output"))
    if (in_tok is None or out_tok is None) and llm_obj is not None:
        for attr in ("last_usage", "usage"):
            u = getattr(llm_obj, attr, None)
            if isinstance(u, dict):
                in_tok = in_tok or u.get("prompt_tokens") or u.get("input_tokens")
                out_tok = out_tok or u.get("completion_tokens") or u.get("output_tokens")
                break
    return in_tok, out_tok, resp_text

def _safe_text(resp_obj):
    if isinstance(resp_obj, str):
        return resp_obj
    if isinstance(resp_obj, dict):
        return (resp_obj.get("text") or resp_obj.get("content") or resp_obj.get("output") or "")
    return str(resp_obj or "")

def _estimate_tokens_rough(text: str):
    return max(1, int(len(text) / 4)) if text else 0

def _cosine_resp_vs_contexts_bge(resp_text: str, contexts: list[str]) -> float:
    if not contexts:
        return 0.0
    import numpy as np
    model = _bge()
    v_resp = model.encode([resp_text], return_dense=True)["dense_vecs"][0]
    v_resp = v_resp / (np.linalg.norm(v_resp) + 1e-12)
    best = 0.0
    for c in contexts:
        v_ctx = model.encode([c], return_dense=True)["dense_vecs"][0]
        v_ctx = v_ctx / (np.linalg.norm(v_ctx) + 1e-12)
        best = max(best, float((v_resp * v_ctx).sum()))
    return best

def _informativeness_len(resp_text: str, lo: int = 60, hi: int = 600) -> float:
    n = len(resp_text or "")
    if n <= lo: return 0.0
    if n >= hi: return 1.0
    return (n - lo) / (hi - lo)

def _trustworthiness_simple(resp_text: str, expected: str, wrong_format_flag: int) -> float:
    t = 0.9
    if wrong_format_flag == 1:
        t -= 0.3
    def _norm(s: str):
        s = unicodedata.normalize("NFKC", s or "").lower().strip()
        s = re.sub(r"\s+", " ", s)
        s = re.sub(r"[^\w\sÀ-ỹ]", "", s)
        return s
    if _norm(expected) in _norm(resp_text):
        t += 0.05
    return float(min(max(t, 0.0), 1.0))

def _triad_eval(question: str, answer: str, contexts: list[str], expected: str, wrong_format_flag: int):
    try:
        relevance = _cosine_resp_vs_contexts_bge(answer, contexts)
    except Exception:
        relevance = 0.7
    trust = _trustworthiness_simple(answer, expected, wrong_format_flag)
    info  = _informativeness_len(answer)
    triad = round((relevance + trust + info) / 3, 4)
    return triad, trust, relevance, info

# ================= Ingest: prototype theo bệnh =================
def ingest_vimedical_by_disease(in_json: str, batch_size: int = 256, max_retries: int = 3) -> int:
    """
    Gom các câu hỏi theo Disease, tạo 1 vector prototype/bệnh (mean pooling),
    payload kèm một số ví dụ để giải thích. Upsert 1 point / bệnh.
    """
    data = json.loads(Path(in_json).read_text(encoding="utf-8"))

    # Gom câu theo bệnh
    by_disease: Dict[str, List[str]] = OrderedDict()
    for item in data:
        d = (item.get("Disease") or "").strip()
        q = (item.get("Question") or "").strip()
        if not d or not q: 
            continue
        by_disease.setdefault(d, []).append(q)

    diseases = list(by_disease.keys())
    emb = EmbeddingGenerator()
    vdb = VectorDB()
    coll = getattr(vdb, "collection", None)
    if not coll:
        raise RuntimeError("Thiếu QDRANT_COLLECTION trong .env")

    import numpy as np
    from qdrant_client.models import PointStruct

    points = []
    idx = 0
    for d, qs in by_disease.items():
        vecs = emb.encode_texts(qs)  # np.ndarray [k, dim]
        centroid = (vecs.mean(axis=0) if hasattr(vecs, "mean") else np.mean(vecs, axis=0)).tolist()

        # ví dụ hiển thị gọn
        examples = qs[:5]
        display_text = f"Disease: {d} | Examples: " + " | ".join(examples[:3])

        payload = {
            "label": d,
            "examples": examples,
            "source": "ViMedical_Disease.json",
            "text": display_text,   # để retriever/UX có gì mà xem
        }
        points.append(PointStruct(id=idx, vector=centroid, payload=payload))
        idx += 1

        if len(points) >= batch_size:
            _upsert_qdrant_batch(vdb, coll, points, max_retries=max_retries)
            points = []

    if points:
        _upsert_qdrant_batch(vdb, coll, points, max_retries=max_retries)

    return len(diseases)

def _upsert_qdrant_batch(vdb, coll, points, max_retries=3):
    attempt = 0
    while True:
        try:
            vdb.client.upsert(collection_name=coll, points=points, wait=True)
            break
        except Exception:
            attempt += 1
            if attempt > max_retries:
                raise
            _time.sleep(1.5 * attempt)

# ================= Agent =================
def build_agent() -> DiagnosisAgent:
    vdb = VectorDB()
    emb = EmbeddingGenerator()
    rr  = ViRanker()
    retr= Retriever(vdb, emb, rr, top_k=8, rerank_k=3)
    llm = LLMGenerator()
    return DiagnosisAgent(retr, llm)

def append_list(path: str, obj: dict) -> None:
    p = Path(path)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = [data]
        except Exception:
            data = []
        data.append(obj)
    else:
        data = [obj]
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ================= Run all =================
def run_all(
    in_json: str,
    unique_json: str,
    out_pretty: str = "eval_outputs.json",
):
    # 1) Ingest theo bệnh (prototype)
    n_ing = ingest_vimedical_by_disease(in_json)
    print(f"📦 Ingest prototype theo bệnh: {n_ing} points (mỗi bệnh 1 point)")

    # 2) Tạo bộ test unique-per-disease
    n_uniq = make_unique_per_disease(in_json, unique_json)
    print(f"🧪 Sinh bộ test: {n_uniq} bệnh -> {unique_json}")

    # 3) Eval
    agent = build_agent()
    Path(out_pretty).unlink(missing_ok=True)
    uniq = json.loads(Path(unique_json).read_text(encoding="utf-8"))

    print(f"▶️ Bắt đầu eval {len(uniq)} bệnh")
    for i, item in enumerate(uniq, 1):
        disease = (item.get("Disease") or "").strip()
        question = (item.get("Question") or "").strip()
        try:
            t0 = time.perf_counter()
            hits = agent.retriever(question)
            t_retr = time.perf_counter() - t0

            # Ưu tiên lấy context từ payload.examples nếu có; fallback về h['text']
            contexts = []
            for h in hits:
                payload = None
                if isinstance(h, dict):
                    payload = h.get("payload")
                    txt = h.get("text")
                else:
                    payload = getattr(h, "payload", None)
                    txt = getattr(h, "text", None)
                if isinstance(payload, dict) and payload.get("examples"):
                    ctx = " | ".join(payload["examples"][:3])
                    contexts.append(f"(Ví dụ) {ctx}")
                elif txt:
                    contexts.append(str(txt))
            msgs = build_diag_prompt(question, contexts)

            t1 = time.perf_counter()
            resp = agent.llm.chat(msgs)
            t_all = time.perf_counter() - t1 + t_retr

            # tokens & response text
            in_tok, out_tok, resp_text_override = _extract_usage_from_resp(resp, getattr(agent, "llm", None))
            resp_text = resp_text_override if resp_text_override is not None else _safe_text(resp)
            if in_tok is None:
                rough_prompt = (msgs[0]["content"] if isinstance(msgs, list) and msgs else "") + \
                               (msgs[1]["content"] if isinstance(msgs, list) and len(msgs) > 1 else "")
                in_tok = _estimate_tokens_rough(rough_prompt)
            if out_tok is None:
                out_tok = _estimate_tokens_rough(resp_text)

            # chấm điểm
            wf = wrong_format_check(resp_text)
            pred = extract_disease_from_answer(resp_text)

            # triad (tính máy)
            triad_score, trustworthiness, relevance, informativeness = _triad_eval(
                question=question, answer=resp_text, contexts=contexts,
                expected=disease, wrong_format_flag=wf
            )

            rec = {
                "question": question,
                "expected_answer": disease,
                "response": resp_text or "",
                "retrieval_seconds": t_retr,
                "runtime_seconds": t_all,

                "input_tokens": in_tok,
                "output_tokens": out_tok,

                "exact_match": exact_match(pred, disease),
                "cosine_similarity": cosine_similarity_bge(pred, disease),
                "bert_f1": bert_f1_vi(pred, disease),

                "triad_score": triad_score,
                "trustworthiness": trustworthiness,
                "relevance": relevance,
                "informativeness": informativeness,

                "wrong_format": wf,
            }
            append_list(out_pretty, rec)
            print(f"[{i}/{len(uniq)}] {disease} → EM={rec['exact_match']}  Cos={rec['cosine_similarity']:.3f}")
        except Exception as e:
            print(f"[{i}] ERROR {disease}: {e}")

    print(f"\n✅ Done. Pretty JSON: {out_pretty}")

if __name__ == "__main__":
    # Đường dẫn theo repo của bạn
    in_json   = os.getenv("VIMEDICAL_JSON", "ViMedical_Disease.json")
    unique_js = os.getenv("VIMEDICAL_UNIQUE_JSON", "ViMedical_Disease_test.json")

    run_all(
        in_json=in_json,
        unique_json=unique_js,
        out_pretty="eval_outputs.json",
    )
