# A2A Medical RAG (Gemma-2-9B-IT + BGE-M3 + Qdrant + ViRanker)

Pipeline tối giản đúng spec: 
- LLM core: Gemma-2-9B-IT (OpenRouter)
- Embedding: BAAI/bge-m3 (FlagEmbedding, local)
- Vector DB: Qdrant Cloud (cosine, 1024d)
- Rerank: ViRanker (CrossEncoder) hoặc Cohere (tùy COHERE_API_KEY)
- Tiền xử lý: pdfplumber -> NFC -> bỏ khoảng trắng thừa -> lowercase -> gộp newline (KHÔNG bỏ stopword)
- Chunking: 1 page, no overlap
- API: FastAPI localhost
- Log: SQLite local

## Cài đặt
```bash
pip install -r requirements.txt
cp .env.example .env
# Chỉnh .env theo Qdrant/OpenRouter của bạn
```

## Chuẩn bị dữ liệu
- Đặt PDF vào: `data/raw_pdfs/`

## Ingest (trích xuất -> embed -> upsert Qdrant)
```bash
python -m scripts.ingest
```

## Chạy API
```bash
uvicorn a2a_medical.app:app --reload --port 8000
```

## Query thử
```bash
curl -X POST http://127.0.0.1:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query":"Tôi đau thượng vị và ợ chua, có thể là gì?"}'
```

## Đánh giá (tuỳ chọn)
- Nếu bạn bật ghi JSONL (xem scripts/eval_ragas.py), có thể dùng RAGAS để tính faithfulness/answer_relevancy.

## Ghi chú
- Nếu muốn dùng VNCoreNLP word-seg, cần Java và model `.jar`. Đặt `USE_VNCORENLP=true` trong `.env` và chuẩn bị thư mục `vncorenlp/` theo hướng dẫn thư viện.
- Đảm bảo Qdrant collection `med_docs_m3` không bị xóa dữ liệu: module sẽ chỉ create-if-not-exists.
- Nếu dùng Cohere Rerank, set `COHERE_API_KEY` trong `.env`.

a2a-host/
├─ host/
│  ├─ main.py               # FastAPI: /orchestrate, /health
│  ├─ registry.py           # Đăng ký các agent (symptom/cost/booking)
│  ├─ policies.py           # Safety cơ bản + mask (đơn giản)
│  └─ schemas.py            # Pydantic: Message, OrchestrateReq/Resp
├─ agents/
│  ├─ symptom_adapter.py    # Adapter gọi RAG tư vấn triệu chứng (HTTP hoặc Python)
│  ├─ cost_stub.py          # Stub: raise NotImplementedError (để sau)
│  └─ booking_stub.py       # Stub: raise NotImplementedError (để sau)
├─ configs/
│  └─ .env.example          # RAG_API_URL=..., AUTH_TOKEN=...
├─ requirements.txt         # fastapi uvicorn pydantic requests python-dotenv
└─ README.md

