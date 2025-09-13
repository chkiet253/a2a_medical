# A2A Medical RAG (Gemma-2-9B-IT + BGE-M3 + Qdrant + ViRanker)

Pipeline tối giản đúng spec: 
- LLM core: Gemma-2-9B-IT (OpenRouter)
- Embedding: BAAI/bge-m3 (FlagEmbedding, local)
- Vector DB: Qdrant Cloud (cosine, 1024d)
- Rerank: ViRanker (CrossEncoder)
- Tiền xử lý: pdfplumber -> NFC -> bỏ khoảng trắng thừa -> lowercase -> gộp newline (KHÔNG bỏ stopword)
- Chunking: 1 page, no overlap
- API: FastAPI localhost
- Log: SQLite local

## Cài đặt
```bash
pip install -r requirements.txt
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


## Project structure

```bash
a2a-medical/
├─ app.py
├─ .env
├─ requirements.txt
└─ a2a_medical/
   ├─ __init__.py
   ├─ host/
   │  ├─ __init__.py
   │  └─ host_agent.py      # Orchestrator: route -> diagnose/schedule/cost
   ├─ diagnose/
   │  ├─ __init__.py
   │  ├─ app.py             # Streamlit (deploy local)
   │  ├─ agent.py           # DiagnosisAgent (từ generator.py)
   │  ├─ generator.py       # LLMGenerator, prompt, parsing
   │  ├─ retriever.py       # Retriever, ViRanker
   │  ├─ embedder.py        # EmbeddingGenerator (BGE-M3)
   │  ├─ vector_db.py       # Qdrant wrapper
   │  └─ preprocessor.py    # PDF -> chunks.jsonl
   ├─ schedule/
   │  ├─ __init__.py
   │  └─ agent.py           # ScheduleAgent (stub)
   └─ cost/
      ├─ __init__.py
      └─ agent.py           # CostAdvisorAgent (stub)


