"""
Unit Tests for Two-Stage Hybrid RAG Pipeline (Module 4).
"""

from pathlib import Path
from src.config import RUNBOOKS_DIR
from src.rag.chunker import ParentChildMarkdownChunker
from src.rag.hybrid_retriever import HybridRAGRetriever
from src.rag.reranker import CrossEncoderReranker
from src.rag.crag_grader import CorrectiveRAGGrader


def test_parent_child_chunker():
    chunker = ParentChildMarkdownChunker()
    chunks = chunker.chunk_directory(RUNBOOKS_DIR)
    assert len(chunks) > 50

    # Ensure parent-child linkage exists
    child_chunks = [c for c in chunks if not c.is_parent]
    assert len(child_chunks) > 0

    first_child = child_chunks[0]
    assert first_child.parent_id is not None
    assert len(first_child.parent_content) > len(first_child.content)


def test_hybrid_retriever_exact_error_code():
    chunker = ParentChildMarkdownChunker()
    chunks = chunker.chunk_directory(RUNBOOKS_DIR)

    retriever = HybridRAGRetriever()
    retriever.index_chunks(chunks)

    # Search for specific error code
    results = retriever.search("ERR_DB_POOL_9045", top_k=3)
    assert len(results) > 0
    top_hit = results[0]
    assert "ERR_DB_POOL_9045" in top_hit["parent_content"] or "PostgreSQL" in top_hit["title"]


def test_crag_grader_marks_correct():
    grader = CorrectiveRAGGrader()
    mock_doc = {
        "title": "PostgreSQL Connection Pool Exhaustion",
        "parent_content": "Runbook detailing ERR_DB_POOL_9045 connection pool exhaustion.",
        "cross_encoder_score": 5.2
    }
    grade = grader.grade_retrieval("ERR_DB_POOL_9045 timeout", [mock_doc], error_code="ERR_DB_POOL_9045")
    assert grade["is_relevant"] is True
    assert grade["grade"] == "CORRECT"
    assert grade["web_fallback_used"] is False

