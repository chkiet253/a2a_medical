import os
from dotenv import load_dotenv
load_dotenv()

from diagnose_agent.vector_db import VectorDB
from diagnose_agent.embedder import EmbeddingGenerator
from diagnose_agent.retriever import Retriever, ViRanker
from diagnose_agent.generator import LLMGenerator, DiagnosisAgent

_vectordb = _embedder = _retriever = _llm = _agent = None

def get_agent_diagnose(top_k: int = 5, rerank_k: int = 2):
    global _vectordb, _embedder, _retriever, _llm, _agent
    if _agent is None:
        _vectordb = VectorDB()
        _embedder = EmbeddingGenerator(use_vncorenlp=True)
        rr = ViRanker()
        _retriever = Retriever(vectordb=_vectordb, embedder=_embedder, reranker=rr,
                               top_k=top_k, rerank_k=rerank_k)
        _llm = LLMGenerator()
        _agent = DiagnosisAgent(retriever=_retriever, llm=_llm)
    return _agent
