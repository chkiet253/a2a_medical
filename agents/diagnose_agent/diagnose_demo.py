import os, sys, pathlib
from dotenv import load_dotenv, find_dotenv
import streamlit as st

# === Paths & sys.path ===
ROOT = pathlib.Path(__file__).resolve().parent
PARENT = ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

# === ENV ===
load_dotenv()
print("[ENV] .env path:", find_dotenv())

# probe Qdrant nhanh (optional)
try:
    import httpx
    print("[ENV] QDRANT_URL=", os.getenv("QDRANT_URL"))
    print("[ENV] QDRANT_COLLECTION=", os.getenv("QDRANT_COLLECTION"))
    r = httpx.get(
        f"{os.getenv('QDRANT_URL')}/collections",
        headers={"api-key": os.getenv("QDRANT_API_KEY","")},
        timeout=30
    )
    print("[QDRANT PROBE]", r.status_code, r.text[:120])
except Exception as e:
    print("[QDRANT PROBE ERROR]", repr(e))

# === Core imports (NO ingest) ===
from diagnose_agent.vector_db import VectorDB
from diagnose_agent.embedder import EmbeddingGenerator
from diagnose_agent.retriever import Retriever, ViRanker
from diagnose_agent.generator import LLMGenerator, DiagnosisAgent     # Gemma (Groq/OpenRouter/Ollama) — bạn đã khoá Gemma

# ================= Helpers (cached) =================
@st.cache_resource(show_spinner=False)
def get_vectordb():
    # Dùng QDRANT_URL / QDRANT_API_KEY / QDRANT_COLLECTION từ .env
    return VectorDB()

@st.cache_resource(show_spinner=False)
def get_query_embedder(device_choice: str = "auto"):
    """
    Encoder chỉ cho QUERY. Nếu index embed bằng text_ws, nên bật VNCoreNLP cho query.
    device_choice: "auto" | "cpu"
    """
    kw = {"use_vncorenlp": False}
    if device_choice == "cpu":
        kw.update({"device": "cpu", "use_fp16": False})
    return EmbeddingGenerator(**kw)

@st.cache_resource(show_spinner=False)
def get_agent(device_choice: str = "auto", top_k: int = 5, rerank_k: int = 2):
    vdb = get_vectordb()
    qemb = get_query_embedder(device_choice)
    rr = ViRanker()  # ViRanker-only
    retr = Retriever(vectordb=vdb, embedder=qemb, reranker=rr, top_k=top_k, rerank_k=rerank_k)
    llm = LLMGenerator()  # Gemma theo .env (groq/openrouter/ollama)
    agent = DiagnosisAgent(retriever=retr, llm=llm)
    return agent

# ================= UI =================
st.set_page_config(page_title="A2A Medical — Chẩn đoán", page_icon="🩺", layout="wide")
st.title("🩺 A2A Medical (RAG)")

with st.sidebar:
    st.subheader("Cấu hình")
    device_choice = st.radio("Thiết bị embed QUERY", ["auto", "cpu"], index=0)
    top_k = st.slider("Top-k từ Vector DB", 1, 20, 5)
    rerank_k = st.slider("Top-k sau ViRanker", 1, 10, 2)

    st.divider()
    st.caption("Thông tin môi trường")
    try:
        import torch
        info = {
            "cuda_available": torch.cuda.is_available(),
            "qdrant_url": os.getenv("QDRANT_URL"),
            "collection": os.getenv("QDRANT_COLLECTION"),
            "llm_provider": os.getenv("LLM_PROVIDER", "groq"),
            "llm_model": os.getenv("GROQ_MODEL") or os.getenv("OPENROUTER_MODEL") or os.getenv("OLLAMA_MODEL") or "gemma",
        }
    except Exception as e:
        info = {"error": str(e)}
    st.json(info)

# ========== Chat history ==========
if "messages" not in st.session_state:
    st.session_state.messages = []

for role, content in st.session_state.messages:
    with st.chat_message(role):
        st.markdown(content)

# ========== Input ==========
query = st.chat_input("Nhập triệu chứng hoặc câu mô tả ca bệnh (tiếng Việt)…")
if query:
    st.session_state.messages.append(("user", query))
    with st.chat_message("user"):
        st.markdown(query)

    agent = get_agent(device_choice=device_choice, top_k=top_k, rerank_k=rerank_k)

    with st.chat_message("assistant"):
        with st.spinner("Đang truy hồi → ViRanker → Gemma chẩn đoán…"):
            try:
                # Agent chẩn đoán 1 bệnh — trả về {"disease","rationale","answer_raw","contexts","model"}
                out = agent.answer(query)

                # Nếu agent của bạn trả "answer" (bản cũ), fallback hiển thị answer
                disease = out.get("disease")
                rationale = out.get("rationale")
                answer_raw = out.get("answer_raw") or out.get("answer", "")

                if disease:
                    st.success(f"🩺 **Chẩn đoán:** {disease}")
                    if rationale:
                        st.write("**Lý do:**", rationale)
                else:
                    # Không đủ dữ kiện hoặc agent chưa tách — hiển thị raw
                    st.markdown(answer_raw or "_Không đủ thông tin trong nguồn_")

                with st.expander("🔎 Context dùng để chẩn đoán (top sau ViRanker)"):
                    for i, c in enumerate(out.get("contexts", []), 1):
                        meta = c.get("meta", {}) or {}
                        # hỗ trợ cả schema mới và cũ
                        name = meta.get("book_name") or meta.get("doc_name") or "?"
                        cid  = meta.get("id") or meta.get("chunk_id") or "?"
                        page = meta.get("page", "?")
                        vecs = meta.get("score")
                        rks  = meta.get("ranker_score")
                        head = f"**Đoạn {i}** — *{name}*, trang {page}, id `{cid}`"
                        if isinstance(vecs, (int, float)): head += f" | vec={vecs:.4f}"
                        if isinstance(rks, (int, float)):  head += f" | rerank={rks:.4f}"
                        st.markdown(head)
                        st.write((c.get("text", "") or "")[:1800])

                # lưu lịch sử (ưu tiên câu trả lời gọn; fallback raw)
                final_display = disease or answer_raw
                st.session_state.messages.append(("assistant", final_display))

            except Exception as e:
                msg = f"Xin lỗi, có lỗi khi chẩn đoán: {e}"
                st.error(msg)
                st.session_state.messages.append(("assistant", msg))