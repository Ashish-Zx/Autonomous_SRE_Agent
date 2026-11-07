"""
FastAPI Production Microservice for SentinelSRE (Module 6 Bridge).
Provides:
- Async Incident Ingestion
- Server-Sent Events (SSE) live streaming of agent investigation progress
- Human-in-the-Loop approval/rejection endpoints
- Long-Term Episodic Memory query API
- In-memory semantic caching for recurring alerts
"""

import sys
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from src.agents.graph import (
    start_incident_investigation,
    resume_with_human_approval,
    sre_agent_app
)
from src.memory.episodic_store import EpisodicIncidentStore
from src.schemas import IncidentAlert, IncidentStatus

app = FastAPI(
    title="SentinelSRE Production Incident API",
    description="Autonomous Multi-Agent Incident Triage Engine REST & SSE Streaming API",
    version="1.0.0"
)

# Enable CORS for external dashboards and microservices
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory Cache for Recurring Alerts (Module 6)
ALERT_SEMANTIC_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


class ApprovalRequest(BaseModel):
    approved: bool
    reason: Optional[str] = "Approved by on-call engineer"


@app.get("/health")
def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    return {
        "status": "HEALTHY",
        "service": "SentinelSRE",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "capabilities": ["multi_agent_triage", "two_stage_hybrid_rag", "mcp_remediation", "episodic_memory"]
    }


@app.post("/api/incidents/triage")
def trigger_triage(alert: IncidentAlert, background_tasks: BackgroundTasks):
    """
    Submits an alert for automated multi-agent investigation.
    Checks semantic cache for recurring alert signatures before launching full graph.
    """
    cache_key = f"{alert.service_name}:{alert.error_code}"
    cached = ALERT_SEMANTIC_CACHE.get(cache_key)

    if cached:
        cache_age = (datetime.now(timezone.utc) - cached["cached_at"]).total_seconds()
        if cache_age < CACHE_TTL_SECONDS:
            return {
                "thread_id": cached["thread_id"],
                "status": "CACHED_RESOLUTION",
                "cache_hit": True,
                "rca_report": cached["state"].get("rca_report"),
                "remediation_result": cached["state"].get("remediation_result")
            }

    thread_id = f"inc-{alert.alert_id}-{int(datetime.now(timezone.utc).timestamp())}"
    alert_dict = alert.model_dump()

    # Run investigation synchronously up to the HITL interrupt gate
    state = start_incident_investigation(alert_dict, thread_id=thread_id)

    # Cache result
    ALERT_SEMANTIC_CACHE[cache_key] = {
        "thread_id": thread_id,
        "state": state,
        "cached_at": datetime.now(timezone.utc)
    }

    return {
        "thread_id": thread_id,
        "status": state.get("status"),
        "findings_count": len(state.get("findings", [])),
        "rca_summary": state.get("rca_report", {}).get("summary") if state.get("rca_report") else None,
        "critic_verified": state.get("critic_eval", {}).get("is_verified", False),
        "awaiting_human_approval": state.get("status") == IncidentStatus.AWAITING_APPROVAL.value,
        "recommended_remediations": state.get("rca_report", {}).get("recommended_remediations", []) if state.get("rca_report") else []
    }


@app.get("/api/incidents/{thread_id}/status")
def get_incident_status(thread_id: str):
    """Retrieves current state of an incident investigation thread from LangGraph checkpointer."""
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = sre_agent_app.get_state(config)

    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail=f"Incident thread '{thread_id}' not found.")

    values = state_snapshot.values
    return {
        "thread_id": thread_id,
        "status": values.get("status"),
        "is_paused_for_approval": bool(state_snapshot.next and "remediation_executor" in state_snapshot.next),
        "findings": values.get("findings", []),
        "rca_report": values.get("rca_report"),
        "critic_eval": values.get("critic_eval"),
        "remediation_result": values.get("remediation_result")
    }


@app.post("/api/incidents/{thread_id}/approve")
def approve_remediation(thread_id: str, payload: ApprovalRequest):
    """
    Submits Human-in-the-Loop decision to resume graph execution past interrupt().
    If approved, executes remediation over FastMCP.
    """
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = sre_agent_app.get_state(config)

    if not state_snapshot or not state_snapshot.next:
        raise HTTPException(status_code=400, detail="No active paused workflow awaiting approval for this thread.")

    resumed_state = resume_with_human_approval(thread_id, approved=payload.approved)

    return {
        "thread_id": thread_id,
        "status": resumed_state.get("status"),
        "remediation_result": resumed_state.get("remediation_result"),
        "episodic_memory_updated": resumed_state.get("status") == IncidentStatus.RESOLVED.value
    }


@app.get("/api/incidents/{thread_id}/stream")
async def stream_incident_events(thread_id: str):
    """
    Server-Sent Events (SSE) endpoint streaming real-time status transitions to web clients.
    """
    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}
        for _ in range(30):  # Poll state transitions for up to 30 seconds
            state_snapshot = sre_agent_app.get_state(config)
            if state_snapshot and state_snapshot.values:
                data = {
                    "status": state_snapshot.values.get("status"),
                    "findings_count": len(state_snapshot.values.get("findings", [])),
                    "is_paused": bool(state_snapshot.next and "remediation_executor" in state_snapshot.next),
                    "has_rca": bool(state_snapshot.values.get("rca_report")),
                }
                yield {"event": "incident_update", "data": json.dumps(data)}

                if state_snapshot.values.get("status") in (IncidentStatus.RESOLVED.value, IncidentStatus.FAILED.value):
                    yield {"event": "incident_finished", "data": json.dumps(state_snapshot.values)}
                    break

            await asyncio.sleep(1.0)

    return EventSourceResponse(event_generator())


@app.get("/api/memory/history")
def get_episodic_memory(service_name: Optional[str] = None, error_code: Optional[str] = None, limit: int = 10):
    """Queries long-term episodic memory store for historical incident resolutions."""
    store = EpisodicIncidentStore()
    history = store.find_similar_resolutions(
        service_name=service_name or "",
        error_code=error_code or "",
        limit=limit
    )
    return {"total": len(history), "incidents": history}

