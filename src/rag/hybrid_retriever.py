"""
Two-Stage Hybrid RAG Retriever (Module 4).
Combines:
1. BM25 Sparse Search (ideal for exact error codes like ERR_DB_POOL_9045 and metric identifiers)
2. FAISS Dense Vector Search (semantic similarity using all-MiniLM-L6-v2)
3. Reciprocal Rank Fusion (RRF) to merge rankings
4. Parent-Child Resolution (returns full parent runbook context for matched child chunks)
"""

import re
from typing import Dict, List, Tuple, Any
import numpy as np
import faiss
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from src.config import (
    EMBEDDING_MODEL_NAME,
    RETRIEVER_BM25_TOP_K,
    RETRIEVER_DENSE_TOP_K,
    RRF_TOP_K
)
from src.rag.chunker import MarkdownDocumentChunk


def tokenize_code_and_text(text: str) -> List[str]:
    """
    Tokenizes text while preserving error codes (e.g., ERR_DB_POOL_9045),
    identifiers, camelCase, and tool names.
    """
    # Normalize lower but keep alphanumeric, underscores, hyphens, and dots
    tokens = re.findall(r"[A-Za-z0-9_\-\.]+", text.lower())
    return tokens


class HybridRAGRetriever:
    """
    Production Hybrid Retriever fusing BM25 and FAISS embeddings via Reciprocal Rank Fusion.
    """

    def __init__(self, embedding_model_name: str = EMBEDDING_MODEL_NAME):
        self.embedding_model_name = embedding_model_name
        self.encoder = SentenceTransformer(embedding_model_name)
        self.chunks: List[MarkdownDocumentChunk] = []
        self.bm25: BM25Okapi = None
        self.faiss_index: faiss.IndexFlatIP = None
        self.parent_map: Dict[str, str] = {}  # parent_id -> parent_content

    def index_chunks(self, chunks: List[MarkdownDocumentChunk]):
        """Indexes child and parent chunks into BM25 and FAISS."""
        self.chunks = chunks
        if not self.chunks:
            return

        # Build parent map for parent-child retrieval
        for c in self.chunks:
            if c.is_parent:
                self.parent_map[c.parent_id] = c.parent_content

        # 1. Build BM25 Corpus
        tokenized_corpus = [tokenize_code_and_text(c.content) for c in self.chunks]
        self.bm25 = BM25Okapi(tokenized_corpus)

        # 2. Build FAISS Dense Index
        corpus_texts = [f"{c.header_path}: {c.content}" for c in self.chunks]
        embeddings = self.encoder.encode(corpus_texts, convert_to_numpy=True, show_progress_bar=False)

        # L2-normalize for Inner Product (Cosine Similarity)
        faiss.normalize_L2(embeddings)
        dim = embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatIP(dim)
        self.faiss_index.add(embeddings.astype(np.float32))

    def _search_bm25(self, query: str, top_k: int = RETRIEVER_BM25_TOP_K) -> List[Tuple[int, float]]:
        tokens = tokenize_code_and_text(query)
        scores = self.bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(idx, float(scores[idx])) for idx in top_indices if scores[idx] > 0.0]

    def _search_dense(self, query: str, top_k: int = RETRIEVER_DENSE_TOP_K) -> List[Tuple[int, float]]:
        query_vector = self.encoder.encode([query], convert_to_numpy=True, show_progress_bar=False)
        faiss.normalize_L2(query_vector)
        scores, indices = self.faiss_index.search(query_vector.astype(np.float32), top_k)
        results = []
        for rank, idx in enumerate(indices[0]):
            if idx >= 0:
                results.append((int(idx), float(scores[0][rank])))
        return results

    def search(self, query: str, top_k: int = RRF_TOP_K, rrf_k: int = 60) -> List[Dict[str, Any]]:
        """
        Executes Reciprocal Rank Fusion between BM25 and FAISS,
        and resolves child chunks to full parent runbook sections.
        """
        bm25_hits = self._search_bm25(query, top_k=RETRIEVER_BM25_TOP_K)
        dense_hits = self._search_dense(query, top_k=RETRIEVER_DENSE_TOP_K)

        # Compute RRF Scores
        rrf_scores: Dict[int, float] = {}

        for rank, (idx, _) in enumerate(bm25_hits, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (1.0 / (rrf_k + rank))

        for rank, (idx, _) in enumerate(dense_hits, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (1.0 / (rrf_k + rank))

        # Sort combined results by RRF score
        sorted_hits = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        # De-duplicate by parent_id to avoid returning multiple snippets of the same runbook section
        seen_parents = set()
        final_results: List[Dict[str, Any]] = []

        for idx, score in sorted_hits:
            chunk = self.chunks[idx]
            parent_id = chunk.parent_id

            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

            parent_text = self.parent_map.get(parent_id, chunk.parent_content)

            final_results.append({
                "chunk_id": chunk.chunk_id,
                "parent_id": parent_id,
                "doc_name": chunk.doc_name,
                "title": chunk.title,
                "header_path": chunk.header_path,
                "matched_snippet": chunk.content,
                "parent_content": parent_text,
                "rrf_score": score,
                "metadata": chunk.metadata,
            })

            if len(final_results) >= top_k:
                break

        return final_results
