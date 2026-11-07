"""
Pydantic v2 Core Schemas for SentinelSRE.
Defines strongly typed data contracts for alerts, parallel worker evidence,
RCA reports, remediation actions, and evaluation metrics.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    P0_CRITICAL = "P0_CRITICAL"
    P1_HIGH = "P1_HIGH"
    P2_MEDIUM = "P2_MEDIUM"
    P3_LOW = "P3_LOW"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    RCA_SYNTHESIZED = "RCA_SYNTHESIZED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"
    FAILED = "FAILED"


class IncidentAlert(BaseModel):
    """Normalized incoming alert triggering an automated SRE investigation."""
    alert_id: str = Field(description="Unique alert identifier (e.g. ALT-9045)")
    service_name: str = Field(description="Name of the affected service (e.g. order-service)")
    environment: str = Field(default="production", description="Environment (production, staging)")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="UTC timestamp")
    error_code: str = Field(description="Standardized error code (e.g. ERR_DB_POOL_9045)")
    title: str = Field(description="One-line summary of the alert")
    raw_message: str = Field(description="Raw alert payload or stack trace excerpt")
    severity: IncidentSeverity = Field(default=IncidentSeverity.P1_HIGH)
    metric_anomalies: Dict[str, Any] = Field(default_factory=dict, description="Key metrics (e.g. {'db_connections': 98})")


class EvidenceCitation(BaseModel):
    """Specific reference to telemetry, commit, or runbook section."""
    source_type: str = Field(description="log, metric, git_commit, runbook, or episodic_memory")
    identifier: str = Field(description="Log timestamp/hash, commit SHA, or runbook header ID")
    snippet: str = Field(description="Extract of the verifying evidence")


class WorkerFinding(BaseModel):
    """Output from an individual specialist investigator node."""
    worker_name: str = Field(description="telemetry_worker, git_worker, or runbook_worker")
    summary: str = Field(description="Key finding from this investigation angle")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score 0.0 to 1.0")
    citations: List[EvidenceCitation] = Field(default_factory=list, description="Citations supporting finding")
    raw_evidence: Dict[str, Any] = Field(default_factory=dict, description="Structured query results")


class RemediationAction(BaseModel):
    """Concrete remediation step to be executed via MCP."""
    action_id: str = Field(description="Unique action ID (e.g. ACT-ROLLBACK-01)")
    tool_name: str = Field(description="MCP tool name (e.g. rollback_service_deployment)")
    service_name: str = Field(description="Target service")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to MCP tool")
    is_destructive: bool = Field(default=False, description="True if action modifies state or risks downtime")
    requires_approval: bool = Field(default=True, description="Enforces Human-in-the-Loop gating")
    rollback_step: Optional[str] = Field(default=None, description="Reversal step if action fails")


class RootCauseReport(BaseModel):
    """Synthesized root cause analysis report cited across all worker evidence."""
    incident_id: str = Field(description="Associated incident identifier")
    service_name: str = Field(description="Affected microservice")
    severity: IncidentSeverity = Field(description="Incident severity")
    summary: str = Field(description="Executive summary of the incident")
    probable_root_cause: str = Field(description="Detailed technical root cause explanation")
    failure_timeline: List[str] = Field(default_factory=list, description="Chronological sequence of failure events")
    citations: List[EvidenceCitation] = Field(default_factory=list, description="Concrete citations from logs/commits/runbooks")
    recommended_remediations: List[RemediationAction] = Field(default_factory=list, description="Step-by-step remediation plan")
    blast_radius: str = Field(description="Assessment of impacted services and user-facing endpoints")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Overall synthesis confidence score")


class CriticEvaluation(BaseModel):
    """Reflexion / Critic verification output validating RCA before human approval."""
    is_verified: bool = Field(description="True if RCA is sufficiently cited and logically coherent")
    loop_count: int = Field(default=0, description="Current iteration of the reflexion loop")
    missing_evidence: List[str] = Field(default_factory=list, description="Evidence gaps requiring another worker pass")
    critique: str = Field(description="Detailed feedback from the critic")
    has_concrete_citations: bool = Field(description="Validates presence of timestamps, commit SHAs, or runbook IDs")


class RemediationResult(BaseModel):
    """Outcome of executing a remediation action via MCP."""
    action_id: str
    tool_name: str
    status: str = Field(description="SUCCESS, FAILED, or REVERTED")
    output_message: str
    executed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    validation_status: Optional[str] = Field(default=None, description="Result of post-remediation health check")


class EvalScore(BaseModel):
    """Evaluation metrics for RAG and agent trajectory."""
    test_id: str
    scenario_name: str
    hit_rate_at_3: float
    mrr: float
    rca_faithfulness: float
    tool_accuracy: float
    latency_seconds: float
    passed: bool
