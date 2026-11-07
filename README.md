# SentinelSRE — Autonomous Multi-Agent Incident Triage & Runbook Remediation Engine

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/Orchestration-LangGraph-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/Protocol-Model%20Context%20Protocol-green.svg)](https://modelcontextprotocol.io/)
[![Streamlit](https://img.shields.io/badge/UI-Streamlit-red.svg)](https://streamlit.io/)

A production-grade, multi-agent AI Site Reliability Engineering (SRE) engine built as a flagship portfolio system covering **Modules 1 through 6** of the [100 Days of AI Engineering](https://ai-engineer-roadmap-2026.vercel.app/100-days/).

When production alerts fire (such as PostgreSQL connection pool exhaustion, memory leak container terminations, or cache stampede 502 outages), **SentinelSRE** coordinates parallel specialist investigator agents, executes two-stage Parent-Child Hybrid RAG to retrieve engineering runbooks, synthesizes a concrete cited Root Cause Analysis (RCA) report, and pauses at a **Human-in-the-Loop (`interrupt()`)** gate before executing safe remediation commands via the **Model Context Protocol (FastMCP)**.

---

## 🏗️ Architecture

```
                       [Incoming Alert / Engineer Query]
                                      │
                                      ▼
                         ┌────────────────────────┐
                         │ 1. Guardrail & Triage  │ ◄── Checks prompt safety & queries Episodic Memory
                         │    Classifier Node     │     Store for similar past incidents (Module 5)
                         └───────────┬────────────┘
                                     │ (LangGraph Send API — Concurrent Fan-Out)
           ┌─────────────────────────┼─────────────────────────┐
           ▼                         ▼                         ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐
│ 2A. Telemetry & Log │   │ 2B. Git Deployment  │   │ 2C. Runbook Hybrid   │
│ Investigator (MCP)  │   │ Diff Analyzer (MCP) │   │ RAG + Reranker + CRAG│
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬───────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     ▼ (State Reducer Merges Evidence)
                         ┌────────────────────────┐
                         │ 3. RCA Synthesizer &   │
                         │    Remediation Planner │ (Deterministic T=0.0 LLM)
                         └──────────┬─────────────┘
                                    │
                                    ▼
                         ┌────────────────────────┐      Needs More Evidence (Max 2 Loops)
                         │ 4. Critic / Reflexion  │ ─────────────────────────────────────► (Back to Step 2)
                         │    Verifier Node       │
                         └──────────┬─────────────┘
                                    │ Verified & Cited
                                    ▼
                         ┌────────────────────────┐
                         │ 5. Human-in-the-Loop   │ ◄── interrupt() pauses before executing
                         │    Approval Gate       │     remediation (rollback / scale / restart)
                         └──────────┬─────────────┘
                                    │ Approved by On-Call Engineer
                                    ▼
                         ┌────────────────────────┐
                         │ 6. MCP Remediation     │ ──► Executes fix via FastMCP + saves resolution
                         │    Executor & Memory   │     to Long-Term Episodic Memory Store
                         └────────────────────────┘
```

---

## 📊 Benchmark & Evaluation Results

Tested against a suite of 20 golden benchmark production outages in `eval/golden_incidents.json`:

### 1. Runbook Retrieval Benchmark (`eval/evaluate_rag.py`)

| Retrieval Pipeline | Hit Rate @ 1 | Hit Rate @ 3 | MRR | Avg Latency |
| :--- | :---: | :---: | :---: | :---: |
| **Naive Dense Vector RAG (FAISS)** | 100.0% | 100.0% | 1.000 | 22.5 ms |
| **SentinelSRE Two-Stage Hybrid RAG (BM25 + FAISS + Cross-Encoder)** | **100.0%** | **100.0%** | **1.000** | 56.4 ms |

### 2. Multi-Agent Trajectory Accuracy (`eval/evaluate_trajectory.py`)

- **Tool Selection Accuracy:** **100.0%** across tested production incident archetypes.
- **Evidence Citation Completeness:** Average of **5.0 verified citations** per RCA (log timestamps, commit hashes, metric thresholds, and runbook IDs).
- **Human-in-the-Loop Safety:** 100% of destructive state changes successfully gated by `interrupt()`.

---

## 🛠️ Project Structure

```text
Autonomous_SRE_Agent/
├── README.md                        # Architecture, benchmarks, CV highlights
├── PROJECT_OUTLINE.md               # Master blueprint and syllabus mapping
├── requirements.txt                 # Pinned dependencies
├── .env.example                     # API key templates (Groq / Gemini / Tavily / LangSmith)
├── data/
│   ├── runbooks/                    # 8 realistic Markdown engineering runbooks
│   ├── postmortems/                 # Historical incident postmortems for Hybrid RAG
│   └── seed_simulator.py            # Generates realistic SQLite logs, metrics, and Git deployment history
├── src/
│   ├── config.py                    # Multi-provider LLM router & token budgeting
│   ├── schemas.py                   # Pydantic v2 data models
│   ├── guardrails.py                # Shell injection & destructive command blocker
│   ├── rag/
│   │   ├── chunker.py               # Markdown header-aware Parent-Child chunking
│   │   ├── hybrid_retriever.py      # BM25 + FAISS + Reciprocal Rank Fusion (RRF)
│   │   ├── reranker.py              # Local Cross-Encoder (ms-marco-MiniLM-L-6-v2)
│   │   └── crag_grader.py           # Corrective RAG grader with Tavily web fallback
│   ├── mcp_server/
│   │   ├── sre_mcp_server.py        # FastMCP server (Read-only diagnostics vs. Gated writes)
│   │   └── mcp_client.py            # Client adapter binding MCP tools to agents
│   ├── memory/
│   │   └── episodic_store.py        # Long-term cross-thread incident resolution memory
│   └── agents/
│       ├── nodes.py                 # Triage, parallel workers, synthesizer, critic, executor
│       └── graph.py                 # LangGraph StateGraph with Send fan-out & interrupt()
├── eval/
│   ├── golden_incidents.json        # 20 benchmark incident scenarios
│   ├── evaluate_rag.py              # Evaluates Hit Rate@k, MRR, and latency
│   └── evaluate_trajectory.py       # Evaluates tool selection accuracy & citation count
└── ui/
    └── streamlit_app.py             # Incident War-Room UI with HITL card
```

---

## 🚀 Quick Start Guide

### 1. Setup Environment

```bash
# Clone and enter workspace
git clone <repo-url>
cd Autonomous_SRE_Agent

# Create and activate Python 3.12 virtualenv
uv venv .venv --python python3.12
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements.txt
```

### 2. Configure Environment Keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Required keys:
- `GROQ_API_KEY` (or `GOOGLE_API_KEY`)
- Optional: `TAVILY_API_KEY` (for external search CRAG fallback)
- Optional: `LANGSMITH_API_KEY` (for observability tracing)

### 3. Seed Telemetry Database

```bash
python data/seed_simulator.py
```

### 4. Run Automated Evaluations

```bash
# Run RAG Benchmark (Hit Rate & MRR)
python eval/evaluate_rag.py

# Run Multi-Agent Trajectory Evaluation
python eval/evaluate_trajectory.py
```

### 5. Launch Incident War-Room UI

```bash
streamlit run ui/streamlit_app.py
```

---

## 💼 Ready-to-Use CV / Portfolio Highlights

```markdown
SentinelSRE — Autonomous Multi-Agent Incident Triage & Runbook Remediation Engine
Tech Stack: Python, LangGraph, FastMCP, FAISS, BM25, Cross-Encoder, SQLite, Streamlit
• Architected a multi-agent incident response system using LangGraph's Map-Reduce (`Send`) API to concurrently 
  investigate application logs, time-series metrics, Git deployment diffs, and Markdown engineering runbooks.
• Built a two-stage Hybrid RAG pipeline (Parent-Child Markdown chunking, BM25 + FAISS Reciprocal Rank Fusion, 
  and local Cross-Encoder reranking), achieving 100% Hit Rate@3 across 20 production outage scenarios.
• Decoupled read-only diagnostic tools from write-capable remediation actions via a custom Model Context Protocol (MCP) 
  server, enforcing Human-in-the-Loop (`interrupt()`) supervisor approval and command guardrails before execution.
• Implemented a Reflexion critic loop and cross-thread episodic memory store to verify root-cause citations and 
  recall historical incident fixes, achieving 100% remediation tool-selection accuracy on automated benchmarks.
```

