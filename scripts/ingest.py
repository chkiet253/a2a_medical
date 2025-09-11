import os
from dotenv import load_dotenv
load_dotenv()

from diagnose_agent.preprocessor import DataPreprocessor
from diagnose_agent.embedder import EmbeddingGenerator
from diagnose_agent.vector_db import VectorDB

if __name__ == "__main__":
    pre = DataPreprocessor(
        in_dir="data/raw_pdfs",
        out_jsonl="data/chunks.jsonl",
        use_vncorenlp=True,                 
   )
    jsonl = pre.build()
    emb = EmbeddingGenerator()
    vdb = VectorDB()
    vdb.upsert_jsonl(jsonl, emb)
    print("Ingest done:", jsonl)
