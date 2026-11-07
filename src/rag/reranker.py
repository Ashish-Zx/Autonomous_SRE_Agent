"""
Cross-Encoder Reranker for Runbook Retrieval (Module 4).
Uses ms-marco-MiniLM-L-6-v2 to evaluate full cross-attention between
the incident symptom query and retrieved runbook sections.
"""

from typing import Dict, List, Any
from sentence_transformers import CrossEncoder

from src.config import RERANKER_MODEL_NAME, RERANKER_FINAL_TOP_K


class CrossEncoderReranker:
    """
    Reranks Hybrid RAG candidate documents with high cross-attention fidelity.
    """

    def __init__(self, model_name: str = RERANKER_MODEL_NAME):
        self.model_name = model_name
        self.reranker = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = RERANKER_FINAL_TOP_K
    ) -> List[Dict[str, Any]]:
        """
        Reranks candidates based on Cross-Encoder scoring.
        Appends 'cross_encoder_score' to each candidate dictionary.
        """
        if not candidates:
            return []

        # Prepare pairs: query vs parent_content (or matched snippet)
        pairs = [[query, c["parent_content"][:1500]] for c in candidates]
        scores = self.reranker.predict(pairs, show_progress_bar=False)

        # Attach scores
        for idx, score in enumerate(scores):
            candidates[idx]["cross_encoder_score"] = float(score)

        # Sort descending by cross-encoder score
        reranked = sorted(candidates, key=lambda x: x["cross_encoder_score"], reverse=True)
        return reranked[:top_k]

