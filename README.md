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
## Cấu trúc thư mục

```mermaid
graph TD
    A[a2a-medical] --> B[app.py]
    A --> C[.env]
    A --> D[requirements.txt]
    A --> E[a2a_medical/]

    E --> E1[__init__.py]

    %% Host
    E --> H[host/]
    H --> H1[__init__.py]
    H --> H2[host_agent.py<br/>(Orchestrator: route → diagnose/schedule/cost)]

    %% Diagnose
    E --> Dg[diagnose/]
    Dg --> Dg1[__init__.py]
    Dg --> Dg2[agent.py<br/>(DiagnosisAgent)]
    Dg --> Dg3[generator.py<br/>(LLMGenerator, prompt, parsing)]
    Dg --> Dg4[retriever.py<br/>(Retriever, ViRanker)]
    Dg --> Dg5[embedder.py<br/>(EmbeddingGenerator BGE-M3)]
    Dg --> Dg6[vector_db.py<br/>(Qdrant wrapper)]
    Dg --> Dg7[preprocessor.py<br/>(PDF → chunks.jsonl)]

    %% Schedule
    E --> S[schedule/]
    S --> S1[__init__.py]
    S --> S2[agent.py<br/>(ScheduleAgent stub)]

    %% Cost
    E --> Cst[cost/]
    Cst --> Cst1[__init__.py]
    Cst --> Cst2[agent.py<br/>(CostAdvisorAgent stub)]

