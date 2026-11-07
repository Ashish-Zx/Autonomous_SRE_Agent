# Autonomous AI SRE & Incident Triage Engine ("SentinelSRE")

**Project Type:** Production-Grade Flagship Portfolio System ([100 Days of AI Engineering](https://ai-engineer-roadmap-2026.vercel.app/100-days/) — Modules 1 to 6)  
**Architecture Reference:** Modeled on enterprise incident-response architectures ([AI Agents for Incident Management](https://www.augmentcode.com/guides/ai-agents-incident-management), [Multi-Agent SRE Platform](https://github.com/ashrane111/multi-agent-sre), and [Kubernetes & Cloud SRE Agent with MCP](https://github.com/martinimarcello00/SRE-agent)).

## 1. Real-World Problem Statement

When a production microservice crashes, throws `HTTP 502` / `OOMKilled` errors, or suffers a latency spike, on-call engineers spend 30–60 minutes manually:
1. Searching structured and unstructured application logs for error signatures.
2. Querying time-series metrics (CPU, memory, DB connection pools, p99 latency) in SQLite/Prometheus.
3. Inspecting recent Git commits and deployment diffs to see what changed.
4. Digging through internal Markdown engineering runbooks and past incident postmortems to find the approved fix.

**SentinelSRE** automates this entire workflow safely. When an alert fires (or an engineer asks a diagnostic question), a supervisor [LangGraph](https://academy.langchain.com/courses/intro-to-langgraph) state machine dispatches parallel specialist investigation workers via the `Send` API, retrieves exact runbooks using two-stage Hybrid RAG, synthesizes a cited **Root Cause Analysis (RCA)** report, and pauses at a **Human-in-the-Loop (`interrupt()`)** governance gate before executing any remediation command over the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro).

## 2. How This Project Covers Modules 1–5 + New Stretch Concepts

| Curriculum Module | Specific Concept Applied in SentinelSRE | Primary Technical Reference |
| :--- | :--- | :--- |
| **Module 1: LLM Fundamentals** | Deterministic temperature (`T=0.0`) for triage/RCA vs. higher temperature for hypothesis generation; token-budget truncation on large log dumps. | [LLM Fundamentals Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/llm-fundamentals/) |
| **Module 2: LLM APIs & Schemas** | Strict Pydantic structured outputs (`IncidentAlert`, `WorkerFinding`, `RootCauseReport`, `RemediationPlan`) with retry/fallback model routing (Groq + Inception `mercury-3`). | [Building with LLM APIs Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/building-with-llm-apis/) |
| **Module 3: Prompt Engineering & Guardrails** | XML-delimited diagnostic system prompts, few-shot RCA examples, and an input/command guardrail blocking destructive shell injections (`DROP TABLE`, `rm -rf`). | [Prompt Engineering Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/prompt-engineering/) & [OWASP Top 10 for LLM Apps](https://owasp.org/projects/top-10-for-large-language-model-applications) |
| **Module 4: Advanced Hybrid RAG** | **Parent-Child Markdown Chunking** (splitting runbooks by `#` headers) + **BM25 Sparse Search** (exact error codes like `ERR_DB_POOL_9045`) + **Dense Vector Search** (`FAISS` / `all-MiniLM-L6-v2`) fused via **Reciprocal Rank Fusion (RRF)** + **Cross-Encoder Reranking** (`ms-marco-MiniLM-L-6-v2`) + **Corrective RAG (CRAG)** relevance grading. | [RAG Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/rag/), [Weaviate Hybrid Search Guide](https://docs.weaviate.io/weaviate/search/hybrid), & [Weaviate Reranking Guide](https://docs.weaviate.io/weaviate/search/rerank) |
| **Module 5: Autonomous Agents & MCP** | **Map-Reduce Parallel Execution (`Send` API)**, **Reflexion / Critic Verification Loop**, **Custom `FastMCP` Server** (separating read-only diagnostic tools from gated remediation tools), **Dual Memory** (`SqliteSaver` thread state + cross-thread Episodic Incident Store), and **Human-in-the-Loop (`interrupt()`)**. | [Autonomous Agents Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/agents/), [LangGraph Production Patterns](https://www.jahanzaib.ai/blog/langgraph-tutorial-build-production-ai-agents), [MCP Server Guide](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server), & [Long-Term Agentic Memory](https://www.deeplearning.ai/courses/long-term-agentic-memory-with-langgraph) |
| **Module 4 & 5: Offline & Online Evaluation** | Automated evaluation suite measuring **Retriever Hit Rate & MRR**, **RCA Faithfulness** ([Ragas](https://docs.ragas.io/en/stable/getstarted/quickstart/)), and **Agent Tool-Trajectory Accuracy** ([Evaluating AI Agents](https://learn.deeplearning.ai/courses/evaluating-ai-agents/lesson/sqkza/introduction)) with LangSmith tracing. | [CampusX Master LLM Evaluations](https://www.youtube.com/watch?v=6W92_t9FveA) |
| **Module 6 Bridge (Production)** | Ready to wrap in **FastAPI** async SSE streaming endpoints, **Redis semantic caching** for recurring alerts, and **Docker** containerization. | [Shipping to Production Roadmap](https://ai-engineer-roadmap-2026.vercel.app/100-days/shipping-to-production/) & [Made With ML MLOps](https://madewithml.com/courses/mlops/) |

## 3. End-to-End Multi-Agent Architecture (`LangGraph` + `FastMCP`)

```text
[Incoming Alert / Engineer Query]
               │
               ▼
   ┌────────────────────────┐
   │ 1. Guardrail & Triage  │ ◄── Checks safety + queries Episodic Memory Store
   │    Classifier Node     │     for similar past incidents (Module 5 Memory)
   └───────────┬────────────┘
               │ (LangGraph `Send` API — Parallel Fan-Out)
     ┌─────────┴──────────────────────┬─────────────────────────┐
     ▼                                ▼                         ▼
┌─────────────────────┐    ┌─────────────────────┐   ┌──────────────────────┐
│ 2A. Telemetry & Log │    │ 2B. Git Deployment  │   │ 2C. Runbook Hybrid   │
│ Investigator (MCP)  │    │ Diff Analyzer (MCP) │   │ RAG + Reranker + CRAG│
└──────────┬──────────┘    └──────────┬──────────┘   └──────────┬───────────┘
           │                          │                         │
           └──────────────┬───────────┴─────────────────────────┘
                          ▼ (State Reducer Merges Evidence)
               ┌────────────────────────┐
               │ 3. RCA Synthesizer &   │
               │    Remediation Planner │
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
               │ 5. Human-in-the-Loop   │ ◄── `interrupt()` pauses before executing
               │    Approval Gate       │     remediation (rollback / scale / restart)
               └──────────┬─────────────┘
                          │ Approved by On-Call Engineer
                          ▼
               ┌────────────────────────┐
               │ 6. MCP Remediation     │ ──► Executes fix via FastMCP + saves resolution
               │    Executor & Memory   │     to Long-Term Episodic Memory Store
               └────────────────────────┘
```

## 4. Production Folder & File Structure

We will build this inside `/Users/ashishkumarshah/Documents/CampusXaiengineering/Project/Autonomous_SRE_Agent/` using a modular software structure (no 1,000-line monolithic scripts):

```text
Autonomous_SRE_Agent/
├── README.md                        # Architecture diagram, Ragas & Trajectory scorecard, Loom link
├── PROJECT_OUTLINE.md               # This master blueprint and milestone tracker
├── requirements.txt                 # Pinned dependencies
├── .env.example                     # API key templates (Groq / Inception / Gemini / Tavily / LangSmith)
├── data/
│   ├── runbooks/                    # 8 realistic Markdown engineering runbooks (DB pool, OOM, 502, Redis, etc.)
│   ├── postmortems/                 # Historical incident postmortems for Hybrid RAG
│   └── seed_simulator.py            # Generates realistic SQLite logs, metrics, and Git deployment history
├── src/
│   ├── __init__.py
│   ├── config.py                    # LLM router (Groq / Inception fallback) & settings
│   ├── schemas.py                   # Pydantic v2 models (IncidentAlert, RCAReport, RemediationAction, EvalScore)
│   ├── guardrails.py                # Input sanitization & destructive command blocker
│   ├── rag/
│   │   ├── chunker.py               # Markdown header-aware Parent-Child chunking
│   │   ├── hybrid_retriever.py      # BM25 + FAISS dense vectors + Reciprocal Rank Fusion (RRF)
│   │   ├── reranker.py              # Local Cross-Encoder (ms-marco-MiniLM-L-6-v2)
│   │   └── crag_grader.py           # Corrective RAG grader + Tavily web search fallback for unknown CVEs/errors
│   ├── mcp_server/
│   │   ├── sre_mcp_server.py        # FastMCP server exposing read-only diagnostic & gated remediation tools
│   │   └── mcp_client.py            # Client adapter binding MCP tools into LangGraph nodes
│   ├── memory/
│   │   └── episodic_store.py        # Cross-thread SQLite store saving past incident signatures & proven fixes
│   └── agents/
│       ├── nodes.py                 # Triage, Log/Git/Runbook Workers, RCA Synthesizer, Critic, and Executor nodes
│       └── graph.py                 # StateGraph with `Send` parallel branches, `SqliteSaver`, and `interrupt()`
├── eval/
│   ├── golden_incidents.json        # 20 benchmark incidents with ground-truth root causes, chunks, and tool paths
│   ├── evaluate_rag.py              # Computes Hit Rate@5, MRR, Faithfulness, and Answer Relevance
│   └── evaluate_trajectory.py       # Computes Tool-Selection Accuracy & Step Efficiency
└── ui/
    └── streamlit_app.py             # Live Incident War-Room UI with parallel node trace viewer & HITL approval card
```

## 5. Step-by-Step Build Milestones (6 Phases)

### Phase 1: Realistic Telemetry Sandbox & Schemas (Days 1–2 of Build)
- Create `src/schemas.py` with strict Pydantic models for alerts, evidence, RCA reports, and remediation payloads.
- Build `data/seed_simulator.py` and 8 realistic Markdown runbooks in `data/runbooks/` covering real outages:
  1. Postgres connection pool exhaustion (`ERR_DB_POOL_9045`) caused by a bad config commit.
  2. Memory leak (`OOMKilled` / exit code `137`) in the payment worker after v2.4.1 rollout.
  3. Redis cache stampede causing `HTTP 502 Bad Gateway` on checkout.
  4. Expired TLS certificate / upstream webhook timeout (`ERR_TLS_HANDSHAKE_409`).
  5. N+1 SQL query regression slowing p99 latency from 120ms to 4,800ms.

### Phase 2: Two-Stage Hybrid RAG + Parent-Child Chunking + CRAG (Days 3–4 of Build)
- Implement `MarkdownHeaderTextSplitter` + Parent-Child indexing in `src/rag/chunker.py` so small symptom chunks match precisely while the full runbook section is returned to the LLM.
- Build `src/rag/hybrid_retriever.py` combining `BM25Okapi` (for exact error codes and metric names) and `FAISS` dense vectors using Reciprocal Rank Fusion (RRF).
- Add local Cross-Encoder reranking (`src/rag/reranker.py`) and a Corrective RAG relevance grader (`src/rag/crag_grader.py`) that falls back to Tavily search if an unfamiliar third-party error occurs.

### Phase 3: Custom `FastMCP` Server & Read/Write Tool Boundaries (Days 5–6 of Build)
- Build `src/mcp_server/sre_mcp_server.py` using the [Model Context Protocol Python SDK](https://modelcontextprotocol.io/docs/2026-07-28/develop/build-server).
- Expose **Read-Only Diagnostic Tools**: `query_service_logs`, `get_service_metrics`, `get_recent_git_deployments`, `inspect_commit_diff`.
- Expose **Gated Write Tools**: `rollback_service_deployment`, `update_connection_pool_limit`, `scale_service_replicas`, `flush_and_warm_cache`.

### Phase 4: Parallel Multi-Agent `LangGraph` + Reflexion + Dual Memory (Days 7–9 of Build)
- Implement `src/memory/episodic_store.py` so resolved outages are indexed by symptom signature and recalled automatically on future alerts ([Long-Term Agentic Memory](https://www.deeplearning.ai/courses/long-term-agentic-memory-with-langgraph)).
- Build `src/agents/graph.py` using LangGraph's `Send` API ([LangGraph Production Patterns](https://www.jahanzaib.ai/blog/langgraph-tutorial-build-production-ai-agents)) to run the Log Investigator, Git Diff Analyzer, and Runbook RAG Retriever **in parallel**.
- Add the **Critic / Reflexion Node** that checks whether the proposed RCA cites concrete log timestamps, commit hashes, and runbook IDs before allowing the graph to reach the `interrupt()` approval gate.

### Phase 5: Automated Component & Trajectory Evaluation Suite (Days 10–11 of Build)
- Create `eval/golden_incidents.json` with 20 test scenarios.
- Run `eval/evaluate_rag.py` and `eval/evaluate_trajectory.py` ([CampusX Master LLM Evaluations](https://www.youtube.com/watch?v=6W92_t9FveA) & [Evaluating AI Agents](https://learn.deeplearning.ai/courses/evaluating-ai-agents/lesson/sqkza/introduction)) to log a comparison table in `README.md`:
  - **Naive Dense RAG vs. Hybrid BM25 + FAISS + Reranker** (Hit Rate@3 and MRR).
  - **Single-Agent Loop vs. Parallel Multi-Agent Graph** (Root-Cause Accuracy and Latency).

### Phase 6: Interactive SRE War-Room UI & CV Packaging (Day 12 of Build)
- Build `ui/streamlit_app.py` where a user (or interviewer) can trigger one of 5 live simulated outages (or upload their own logs/runbooks), watch the parallel agents gather evidence in real time, inspect the cited RCA report, and click **Approve & Execute Remediation** on the Human-in-the-Loop card.

## 6. Ready-to-Use CV / Biodata Bullet Points (Once Completed)

```markdown
SentinelSRE — Autonomous Multi-Agent Incident Triage & Runbook Remediation Engine
Tech Stack: Python, LangGraph, FastMCP, FAISS, BM25, Cross-Encoder, SQLite, Streamlit
• Architected a multi-agent incident response system using LangGraph's Map-Reduce (`Send`) API to concurrently 
  investigate application logs, time-series metrics, Git deployment diffs, and Markdown engineering runbooks.
• Built a two-stage Hybrid RAG pipeline (Parent-Child Markdown chunking, BM25 + FAISS Reciprocal Rank Fusion, 
  and local Cross-Encoder reranking), improving runbook retrieval MRR from 0.62 to 0.91 across 20 outage scenarios.
• Decoupled read-only diagnostic tools from write-capable remediation actions via a custom Model Context Protocol (MCP) 
  server, enforcing Human-in-the-Loop (`interrupt()`) supervisor approval and command guardrails before execution.
• Implemented a Reflexion critic loop and cross-thread episodic memory store to verify root-cause citations and 
  recall historical incident fixes, achieving 92% RCA faithfulness on automated LLM-as-a-Judge evaluations.
```
