"""
Automated RAG Evaluation Suite (Module 4 & 5).
Benchmarks:
1. Baseline Naive Dense Vector Retrieval (FAISS alone)
VS.
2. Two-Stage Hybrid RAG (Parent-Child + BM25 + FAISS + RRF + Cross-Encoder Reranker)

Measures:
- Hit Rate @ 1
- Hit Rate @ 3
- Mean Reciprocal Rank (MRR)
- Average Query Latency
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, List, Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from tabulate import tabulate

from src.config import RUNBOOKS_DIR, EMBEDDING_MODEL_NAME
from src.rag.chunker import ParentChildMarkdownChunker
from src.rag.hybrid_retriever import HybridRAGRetriever
from src.rag.reranker import CrossEncoderReranker

GOLDEN_BENCHMARK_PATH = Path(__file__).resolve().parent / "golden_incidents.json"


def evaluate_naive_dense(test_cases: List[Dict[str, Any]], runbooks_dir: Path) -> Dict[str, float]:
    """Evaluates standard single-stage dense retrieval baseline."""
    # Chunk runbooks with basic fixed-size splitting
    encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
    docs = []
    metadata_list = []

    for file in sorted(runbooks_dir.glob("*.md")):
        text = file.read_text(encoding="utf-8")
        # Extract runbook ID
        rb_id = "UNKNOWN"
        for line in text.splitlines():
            if "**Runbook ID:**" in line:
                rb_id = line.split("**Runbook ID:**")[1].strip()
                break
        docs.append(text)
        metadata_list.append({"runbook_id": rb_id, "file_name": file.name})

    embeddings = encoder.encode(docs, convert_to_numpy=True, show_progress_bar=False)
    faiss.normalize_L2(embeddings)
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings.astype(np.float32))

    hit_1 = 0
    hit_3 = 0
    reciprocal_ranks = []
    latencies = []

    for tc in test_cases:
        query = tc["query"]
        target_id = tc["ground_truth_runbook_id"]

        start_time = time.perf_counter()
        q_vec = encoder.encode([query], convert_to_numpy=True, show_progress_bar=False)
        faiss.normalize_L2(q_vec)
        _, indices = index.search(q_vec.astype(np.float32), 5)
        latency = (time.perf_counter() - start_time) * 1000
        latencies.append(latency)

        retrieved_ids = [metadata_list[idx]["runbook_id"] for idx in indices[0] if idx >= 0]

        # Check ranking
        if retrieved_ids and retrieved_ids[0] == target_id:
            hit_1 += 1

        if target_id in retrieved_ids[:3]:
            hit_3 += 1

        if target_id in retrieved_ids:
            rank = retrieved_ids.index(target_id) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(test_cases)
    return {
        "hit_rate_at_1": (hit_1 / n) * 100,
        "hit_rate_at_3": (hit_3 / n) * 100,
        "mrr": float(np.mean(reciprocal_ranks)),
        "avg_latency_ms": float(np.mean(latencies))
    }


def evaluate_hybrid_rag(test_cases: List[Dict[str, Any]], runbooks_dir: Path) -> Dict[str, float]:
    """Evaluates Two-Stage Hybrid RAG (Parent-Child + BM25 + FAISS + RRF + Cross-Encoder)."""
    chunker = ParentChildMarkdownChunker()
    chunks = chunker.chunk_directory(runbooks_dir)

    retriever = HybridRAGRetriever()
    retriever.index_chunks(chunks)
    reranker = CrossEncoderReranker()

    hit_1 = 0
    hit_3 = 0
    reciprocal_ranks = []
    latencies = []

    for tc in test_cases:
        query = tc["query"]
        target_id = tc["ground_truth_runbook_id"]

        start_time = time.perf_counter()
        raw_hits = retriever.search(query=query, top_k=6)
        reranked_hits = reranker.rerank(query=query, candidates=raw_hits, top_k=5)
        latency = (time.perf_counter() - start_time) * 1000
        latencies.append(latency)

        retrieved_ids = [h.get("metadata", {}).get("runbook_id") for h in reranked_hits]

        if retrieved_ids and retrieved_ids[0] == target_id:
            hit_1 += 1

        if target_id in retrieved_ids[:3]:
            hit_3 += 1

        if target_id in retrieved_ids:
            rank = retrieved_ids.index(target_id) + 1
            reciprocal_ranks.append(1.0 / rank)
        else:
            reciprocal_ranks.append(0.0)

    n = len(test_cases)
    return {
        "hit_rate_at_1": (hit_1 / n) * 100,
        "hit_rate_at_3": (hit_3 / n) * 100,
        "mrr": float(np.mean(reciprocal_ranks)),
        "avg_latency_ms": float(np.mean(latencies))
    }


def run_benchmark():
    test_cases = json.loads(GOLDEN_BENCHMARK_PATH.read_text(encoding="utf-8"))
    print(f"\n=======================================================")
    print(f"[*] Running SentinelSRE Benchmark across {len(test_cases)} Golden Incidents")
    print(f"=======================================================\n")

    print("[1/2] Benchmarking Naive Dense Vector Retrieval (FAISS)...")
    naive_metrics = evaluate_naive_dense(test_cases, RUNBOOKS_DIR)

    print("[2/2] Benchmarking SentinelSRE Two-Stage Hybrid RAG (BM25 + FAISS + Reranker)...")
    hybrid_metrics = evaluate_hybrid_rag(test_cases, RUNBOOKS_DIR)

    table = [
        [
            "Naive Dense Vector RAG (FAISS)",
            f"{naive_metrics['hit_rate_at_1']:.1f}%",
            f"{naive_metrics['hit_rate_at_3']:.1f}%",
            f"{naive_metrics['mrr']:.3f}",
            f"{naive_metrics['avg_latency_ms']:.1f} ms"
        ],
        [
            "SentinelSRE Two-Stage Hybrid RAG",
            f"{hybrid_metrics['hit_rate_at_1']:.1f}%",
            f"{hybrid_metrics['hit_rate_at_3']:.1f}%",
            f"{hybrid_metrics['mrr']:.3f}",
            f"{hybrid_metrics['avg_latency_ms']:.1f} ms"
        ]
    ]

    headers = ["Retrieval Pipeline", "Hit Rate @ 1", "Hit Rate @ 3", "MRR", "Avg Latency"]
    print("\n" + tabulate(table, headers=headers, tablefmt="github") + "\n")


if __name__ == "__main__":
    run_benchmark()
