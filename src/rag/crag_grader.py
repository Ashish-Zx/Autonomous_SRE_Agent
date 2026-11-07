"""
Corrective RAG (CRAG) Grader with Web Fallback (Module 4).
Grades the relevance of retrieved runbook passages.
If internal runbooks do not match the incident symptoms or error code,
falls back to Tavily web search to query external vendor documentation/CVEs.
"""

import os
from typing import Dict, List, Any, Optional
from tavily import TavilyClient

from src.config import CRAG_RELEVANCE_THRESHOLD


class CorrectiveRAGGrader:
    """
    Evaluates retrieved runbook documents and handles fallback correction.
    """

    def __init__(self, threshold: float = CRAG_RELEVANCE_THRESHOLD):
        self.threshold = threshold
        tavily_key = os.getenv("TAVILY_API_KEY")
        self.tavily_client = TavilyClient(api_key=tavily_key) if tavily_key and not tavily_key.startswith("your_") else None

    def grade_retrieval(
        self,
        query: str,
        retrieved_docs: List[Dict[str, Any]],
        error_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Grades retrieved documentation relevance.
        Returns:
            - is_relevant: bool
            - grade: 'CORRECT' | 'AMBIGUOUS' | 'INCORRECT'
            - documents: List[Dict]
            - web_fallback_used: bool
            - fallback_summary: str
        """
        if not retrieved_docs:
            return self._execute_fallback(query, error_code, reason="No internal runbooks matched query.")

        top_doc = retrieved_docs[0]
        # Check cross-encoder score if available, otherwise RRF score
        score = top_doc.get("cross_encoder_score")
        if score is None:
            score = top_doc.get("rrf_score", 0.0)

        # Cross-encoder scores for ms-marco generally range from negative to positive values (e.g. > -1.0 or sigmoid > 0.4)
        is_relevant = score >= self.threshold

        # If exact error code is explicitly mentioned in the doc, guarantee relevance
        if error_code and error_code in top_doc.get("parent_content", ""):
            is_relevant = True

        if is_relevant:
            return {
                "is_relevant": True,
                "grade": "CORRECT",
                "score": score,
                "documents": retrieved_docs,
                "web_fallback_used": False,
                "fallback_summary": None
            }
        else:
            return self._execute_fallback(
                query,
                error_code,
                reason=f"Top retrieved doc score ({score:.3f}) below threshold ({self.threshold})."
            )

    def _execute_fallback(self, query: str, error_code: Optional[str], reason: str) -> Dict[str, Any]:
        """Queries Tavily external search if internal runbooks are insufficient."""
        search_query = f"{error_code} {query} site:stackoverflow.com OR site:github.com OR troubleshooting runbook" if error_code else f"{query} SRE troubleshooting"

        web_results = []
        summary = ""

        if self.tavily_client:
            try:
                response = self.tavily_client.search(
                    query=search_query,
                    search_depth="advanced",
                    max_results=3
                )
                web_results = response.get("results", [])
                summary = f"CRAG Web Fallback Search for '{search_query}':\n" + "\n".join(
                    [f"- [{r.get('title')}]({r.get('url')}): {r.get('content')[:300]}" for r in web_results]
                )
            except Exception as e:
                summary = f"Tavily search attempt failed: {e}. Internal runbook fallback advised."
        else:
            summary = f"No external search API key configured. Reason: {reason}. Manual runbook escalation suggested."

        fallback_doc = {
            "chunk_id": "CRAG_WEB_FALLBACK",
            "parent_id": "CRAG_WEB_FALLBACK",
            "doc_name": "Tavily_Web_Fallback",
            "title": "External Diagnostic Intelligence",
            "header_path": "External Web Search > Diagnostic Fallback",
            "matched_snippet": summary,
            "parent_content": summary,
            "cross_encoder_score": 0.5,
            "metadata": {"source": "tavily_crag"}
        }

        return {
            "is_relevant": False,
            "grade": "INCORRECT",
            "score": 0.0,
            "documents": [fallback_doc],
            "web_fallback_used": True,
            "fallback_summary": summary
        }

