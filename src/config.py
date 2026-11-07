"""
Configuration, Environment Settings, and Multi-LLM Router for SentinelSRE.
Supports primary (Groq), secondary (Gemini), and fallback (Inception) providers
with deterministic token-budgeting and temperature policies.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load local environment variables from .env
load_dotenv(override=True)

# Project Roots
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNBOOKS_DIR = DATA_DIR / "runbooks"
POSTMORTEMS_DIR = DATA_DIR / "postmortems"

# Database Locations
SIMULATOR_DB_PATH = DATA_DIR / "sre_simulator.db"
EPISODIC_MEMORY_DB_PATH = DATA_DIR / "episodic_memory.db"
CHECKPOINT_DB_PATH = DATA_DIR / "checkpoints.db"

# LLM Temperature Policies (Module 1)
TEMPERATURE_DETERMINISTIC: float = 0.0   # Triage, RCA synthesis, critic verification, evaluation
TEMPERATURE_HYPOTHESIS: float = 0.3      # Exploratory hypothesis generation

# Context Window & Token Budgeting (Module 1)
MAX_LOG_EXCERPT_LINES: int = 120
MAX_COMMIT_DIFF_CHARS: int = 4000
MAX_RUNBOOK_CONTEXT_CHARS: int = 6000

# Hybrid RAG & Vector Search Settings (Module 4)
EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
RERANKER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RETRIEVER_BM25_TOP_K: int = 10
RETRIEVER_DENSE_TOP_K: int = 10
RRF_TOP_K: int = 6
RERANKER_FINAL_TOP_K: int = 3
CRAG_RELEVANCE_THRESHOLD: float = 0.40

# Reflexion Settings (Module 5)
MAX_REFLEXION_LOOPS: int = 2

# FastMCP Server Connection Settings
MCP_SERVER_HOST: str = "127.0.0.1"
MCP_SERVER_PORT: int = 8765


class LLMRouter:
    """
    Resilient Multi-Provider LLM Router with automatic fallbacks.
    Priority: Groq (fast) -> Google Gemini (multimodal/reasoning) -> Inception.
    """

    @classmethod
    def get_llm(cls, temperature: float = TEMPERATURE_DETERMINISTIC, preferred_provider: Optional[str] = None):
        """
        Returns an initialized LangChain BaseChatModel instance.
        Falls back gracefully if the preferred or primary provider is unavailable.
        """
        groq_key = os.getenv("GROQ_API_KEY")
        google_key = os.getenv("GOOGLE_API_KEY")
        inception_key = os.getenv("INCEPTION_API_KEY")

        # 1. Groq Preferred or Default
        if (preferred_provider == "groq" or not preferred_provider) and groq_key and not groq_key.startswith("your_"):
            try:
                from langchain_groq import ChatGroq
                return ChatGroq(
                    model_name="openai/gpt-oss-120b",
                    temperature=temperature,
                    api_key=groq_key,
                    max_retries=2,
                )
            except Exception as e:
                print(f"[LLMRouter Warning] Groq init failed ({e}), trying fallback provider...")

        # 2. Google Gemini Fallback
        if (preferred_provider == "google" or not preferred_provider) and google_key and not google_key.startswith("your_"):
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    temperature=temperature,
                    google_api_key=google_key,
                    max_retries=2,
                )
            except Exception as e:
                print(f"[LLMRouter Warning] Gemini init failed ({e}), trying Inception...")

        # 3. Inception Fallback (OpenAI compatible endpoint)
        if inception_key and not inception_key.startswith("your_"):
            try:
                from langchain_openai import ChatOpenAI
                return ChatOpenAI(
                    model="mercury-3",
                    temperature=temperature,
                    api_key=inception_key,
                    base_url=os.getenv("INCEPTION_BASE_URL", "https://api.inceptionai.com/v1"),
                )
            except Exception as e:
                print(f"[LLMRouter Warning] Inception init failed: {e}")

        # If keys are missing in mock/offline mode, return a dummy or raise informative error
        raise RuntimeError(
            "No valid LLM provider keys configured in .env! "
            "Please configure GROQ_API_KEY or GOOGLE_API_KEY in Autonomous_SRE_Agent/.env"
        )
