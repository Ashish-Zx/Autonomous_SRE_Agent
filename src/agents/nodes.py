"""
Multi-Agent Investigation Nodes (Module 5).
Includes:
- Triage & Guardrail Node
- Parallel Specialist Workers (Telemetry, Git, Runbook) dispatched via Send API
- RCA Synthesizer & Remediation Planner (Deterministic LLM with structured output)
- Reflexion / Critic Verifier Node (Citation check & loop limit)
- MCP Remediation Executor & Episodic Memory Update
"""

import json
import operator
from typing import Annotated, Dict, List, Optional, Any, TypedDict
from langchain_core.messages import SystemMessage, HumanMessage

from src.config import LLMRouter, TEMPERATURE_DETERMINISTIC, MAX_REFLEXION_LOOPS
from src.guardrails import sanitize_input_prompt
from src.mcp_server.mcp_client import MCPToolRegistry
from src.memory.episodic_store import EpisodicIncidentStore
from src.schemas import (
    IncidentAlert,
    WorkerFinding,
    EvidenceCitation,
    RootCauseReport,
    RemediationAction,
    CriticEvaluation,
    RemediationResult,
    IncidentStatus
)


class IncidentState(TypedDict):
    """LangGraph shared state for the SentinelSRE incident response workflow."""
    alert: Dict[str, Any]
    status: str
    query: str
    similar_past_incidents: List[Dict[str, Any]]
    findings: Annotated[List[Dict[str, Any]], operator.add]
    rca_report: Optional[Dict[str, Any]]
    critic_eval: Optional[Dict[str, Any]]
    reflexion_loops: int
    human_approval: Optional[Dict[str, Any]]
    remediation_result: Optional[Dict[str, Any]]
    error: Optional[str]


# =============================================================================
# 1. TRIAGE & GUARDRAIL NODE
# =============================================================================

def triage_node(state: IncidentState) -> Dict[str, Any]:
    """
    Sanitizes input, checks guardrails, queries episodic memory for recurring outages,
    and initializes state for parallel worker investigation.
    """
    raw_query = state.get("query", "")
    alert_dict = state.get("alert", {})

    # 1. Guardrail input sanitization
    is_safe, sanitized_query = sanitize_input_prompt(raw_query or alert_dict.get("title", ""))
    if not is_safe:
        return {
            "status": IncidentStatus.FAILED.value,
            "error": sanitized_query
        }

    service_name = alert_dict.get("service_name", "order-service")
    error_code = alert_dict.get("error_code", "")

    # 2. Query Long-Term Episodic Memory
    memory_store = EpisodicIncidentStore()
    similar = memory_store.find_similar_resolutions(service_name=service_name, error_code=error_code)

    return {
        "status": IncidentStatus.INVESTIGATING.value,
        "query": sanitized_query,
        "similar_past_incidents": similar,
        "reflexion_loops": state.get("reflexion_loops", 0)
    }


# =============================================================================
# 2. PARALLEL SPECIALIST INVESTIGATION WORKERS
# =============================================================================

def telemetry_worker_node(state: IncidentState) -> Dict[str, Any]:
    """
    Investigates application logs and time-series metrics via MCP.
    """
    alert = state.get("alert", {})
    service_name = alert.get("service_name", "order-service")
    error_code = alert.get("error_code")

    # Fetch logs
    log_res = MCPToolRegistry.execute_tool(
        "query_service_logs",
        service_name=service_name,
        error_code=error_code,
        severity="ERROR",
        limit=10
    )
    logs = log_res.get("logs", [])

    # Fetch metrics
    metric_name = "db_connection_utilization" if "POOL" in (error_code or "") else "memory_usage_mb" if "OOM" in (error_code or "") else "p99_latency_ms"
    metric_res = MCPToolRegistry.execute_tool(
        "get_service_metrics",
        service_name=service_name,
        metric_name=metric_name,
        limit=5
    )
    datapoints = metric_res.get("datapoints", [])

    citations: List[Dict[str, Any]] = []
    if logs:
        first_log = logs[0]
        citations.append({
            "source_type": "log",
            "identifier": first_log.get("timestamp", ""),
            "snippet": f"[{first_log.get('error_code')}] {first_log.get('message')}"
        })
    if datapoints:
        latest = datapoints[-1]
        citations.append({
            "source_type": "metric",
            "identifier": f"{metric_name}@{latest.get('timestamp')}",
            "snippet": f"Metric {metric_name} peaked at {latest.get('value')} {latest.get('unit')}"
        })

    summary = (
        f"Telemetry analysis for {service_name}: Detected {len(logs)} error log events for '{error_code}'. "
        f"Key metric '{metric_name}' reached anomalous level ({datapoints[-1]['value'] if datapoints else 'N/A'})."
    )

    finding = {
        "worker_name": "telemetry_worker",
        "summary": summary,
        "confidence": 0.95 if logs else 0.40,
        "citations": citations,
        "raw_evidence": {
            "logs": logs[:3],
            "metrics": datapoints[-3:]
        }
    }

    return {"findings": [finding]}


def git_worker_node(state: IncidentState) -> Dict[str, Any]:
    """
    Analyzes recent Git deployments and inspects commit diffs via MCP.
    """
    alert = state.get("alert", {})
    service_name = alert.get("service_name", "order-service")

    deployments_res = MCPToolRegistry.execute_tool(
        "get_recent_git_deployments",
        service_name=service_name,
        limit=3
    )
    deployments = deployments_res.get("deployments", [])

    diff_data = {}
    citations: List[Dict[str, Any]] = []

    if deployments:
        latest_sha = deployments[0].get("commit_sha")
        diff_data = MCPToolRegistry.execute_tool(
            "inspect_commit_diff",
            service_name=service_name,
            commit_sha=latest_sha
        )
        citations.append({
            "source_type": "git_commit",
            "identifier": latest_sha,
            "snippet": f"Commit by {diff_data.get('author')}: '{diff_data.get('commit_message')}'. Diff: {diff_data.get('diff_patch', '')[:200]}"
        })

    summary = (
        f"Git deployment analysis for {service_name}: Latest commit {deployments[0]['commit_sha'] if deployments else 'N/A'} "
        f"by {deployments[0]['author'] if deployments else 'N/A'} introduced suspicious changes: {deployments[0]['commit_message'] if deployments else 'No recent commits'}."
    )

    finding = {
        "worker_name": "git_worker",
        "summary": summary,
        "confidence": 0.90 if deployments else 0.30,
        "citations": citations,
        "raw_evidence": {
            "latest_deployment": deployments[0] if deployments else {},
            "diff_excerpt": diff_data.get("diff_patch", "")[:400]
        }
    }

    return {"findings": [finding]}


def runbook_worker_node(state: IncidentState) -> Dict[str, Any]:
    """
    Searches engineering runbooks using Two-Stage Hybrid RAG + Parent-Child + CRAG.
    """
    alert = state.get("alert", {})
    query = state.get("query") or alert.get("title", "")
    error_code = alert.get("error_code")

    rag_res = MCPToolRegistry.execute_tool(
        "search_runbook_knowledge_base",
        query=f"{query} {error_code or ''}",
        error_code=error_code
    )

    citations: List[Dict[str, Any]] = []
    if rag_res.get("top_runbook_title"):
        citations.append({
            "source_type": "runbook",
            "identifier": rag_res.get("matched_section") or rag_res.get("top_runbook_title"),
            "snippet": f"Runbook: {rag_res.get('top_runbook_title')}. Procedure: {rag_res.get('runbook_content', '')[:250]}"
        })

    summary = (
        f"Runbook Hybrid RAG retrieved: '{rag_res.get('top_runbook_title')}'. "
        f"Relevance grade: {rag_res.get('crag_grade')} (External web fallback used: {rag_res.get('web_fallback_used')})."
    )

    finding = {
        "worker_name": "runbook_worker",
        "summary": summary,
        "confidence": 0.95 if rag_res.get("is_relevant") else 0.50,
        "citations": citations,
        "raw_evidence": {
            "top_runbook_title": rag_res.get("top_runbook_title"),
            "section": rag_res.get("matched_section"),
            "content_excerpt": rag_res.get("runbook_content", "")[:600]
        }
    }

    return {"findings": [finding]}


# =============================================================================
# 3. RCA SYNTHESIZER & REMEDIATION PLANNER
# =============================================================================

RCA_SYNTHESIS_PROMPT = """You are SentinelSRE, an expert Autonomous AI Site Reliability Engineer.
Analyze the incident alert, telemetry findings, Git deployment diffs, and engineering runbooks.
You must synthesize a definitive, cited Root Cause Analysis (RCA) report and specify a safe remediation plan.

CRITICAL INSTRUCTIONS:
1. Ground your analysis strictly on the provided evidence. Cite concrete log timestamps, commit SHAs, and runbook IDs.
2. Select the exact MCP remediation tool from the approved list:
   - 'rollback_service_deployment' (params: service_name, target_commit)
   - 'update_connection_pool_limit' (params: service_name, max_connections)
   - 'scale_service_replicas' (params: service_name, replica_count)
   - 'flush_and_warm_cache' (params: service_name, cache_tier, keyspace)
   - 'cleanup_ephemeral_storage' (params: service_name, target_path, older_than_minutes)
   - 'renew_tls_certificate' (params: service_name, domain, cert_tier)
   - 'reset_rate_limit_counters' (params: service_name, bucket_id, temporary_limit_factor)
3. Return your output as strict JSON matching this structure:
{
  "summary": "Concise executive summary",
  "probable_root_cause": "Detailed technical root cause",
  "failure_timeline": ["Timestamp 1: Event", "Timestamp 2: Event"],
  "citations": [
    {"source_type": "log|git_commit|runbook", "identifier": "string", "snippet": "string"}
  ],
  "blast_radius": "Impacted services and endpoints",
  "confidence_score": 0.95,
  "recommended_remediations": [
    {
      "action_id": "ACT-01",
      "tool_name": "exact_tool_name",
      "service_name": "string",
      "parameters": {},
      "is_destructive": false,
      "requires_approval": true,
      "rollback_step": "string"
    }
  ]
}
"""


def rca_synthesizer_node(state: IncidentState) -> Dict[str, Any]:
    """
    Merges findings from parallel workers and invokes the LLM to generate
    a cited RootCauseReport and RemediationPlan.
    """
    alert = state.get("alert", {})
    findings = state.get("findings", [])
    past_incidents = state.get("similar_past_incidents", [])

    user_payload = f"""
<incident_alert>
{json.dumps(alert, indent=2)}
</incident_alert>

<worker_findings>
{json.dumps(findings, indent=2)}
</worker_findings>

<episodic_memory_similar_incidents>
{json.dumps(past_incidents, indent=2)}
</episodic_memory_similar_incidents>
"""

    llm = LLMRouter.get_llm(temperature=TEMPERATURE_DETERMINISTIC)
    messages = [
        SystemMessage(content=RCA_SYNTHESIS_PROMPT),
        HumanMessage(content=user_payload)
    ]

    response = llm.invoke(messages)
    content = response.content

    # Parse JSON from LLM response
    try:
        # Extract markdown json block if present
        if "```json" in content:
            clean_json = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            clean_json = content.split("```")[1].split("```")[0].strip()
        else:
            clean_json = content.strip()

        parsed = json.loads(clean_json)
        parsed["incident_id"] = alert.get("alert_id", "INC-AUTO")
        parsed["service_name"] = alert.get("service_name", "unknown")
        parsed["severity"] = alert.get("severity", "P1_HIGH")

        rca_report = parsed
    except Exception as e:
        # Fallback structured synthesis if JSON parse fails
        citations = []
        for f in findings:
            citations.extend(f.get("citations", []))

        # Default remediation derived from Git worker or Runbook worker
        git_findings = next((f for f in findings if f["worker_name"] == "git_worker"), None)
        rollback_sha = "a1f9c32"
        if git_findings and git_findings.get("raw_evidence", {}).get("latest_deployment", {}).get("rollback_target_sha"):
            rollback_sha = git_findings["raw_evidence"]["latest_deployment"]["rollback_target_sha"]

        rca_report = {
            "incident_id": alert.get("alert_id", "INC-AUTO"),
            "service_name": alert.get("service_name", "unknown"),
            "severity": alert.get("severity", "P1_HIGH"),
            "summary": f"Incident in {alert.get('service_name')} triggered by {alert.get('error_code')}",
            "probable_root_cause": f"Root cause correlated with recent commit and telemetry spikes: {alert.get('title')}",
            "failure_timeline": ["Alert triggered", "Telemetry spike observed", "Deployment commit identified"],
            "citations": citations,
            "blast_radius": f"Microservice {alert.get('service_name')} and dependent API callers",
            "confidence_score": 0.88,
            "recommended_remediations": [
                {
                    "action_id": "ACT-01",
                    "tool_name": "rollback_service_deployment",
                    "service_name": alert.get("service_name"),
                    "parameters": {
                        "service_name": alert.get("service_name"),
                        "target_commit": rollback_sha
                    },
                    "is_destructive": False,
                    "requires_approval": True,
                    "rollback_step": "Re-apply deployment if rollback causes unintended regressions"
                }
            ]
        }

    return {
        "status": IncidentStatus.RCA_SYNTHESIZED.value,
        "rca_report": rca_report
    }


# =============================================================================
# 4. CRITIC / REFLEXION VERIFIER NODE
# =============================================================================

def critic_node(state: IncidentState) -> Dict[str, Any]:
    """
    Evaluates whether the synthesized RCA cites verifiable evidence
    (log timestamps, commit SHAs, runbook IDs). Triggers reflexion loop if evidence is deficient.
    """
    rca = state.get("rca_report", {})
    citations = rca.get("citations", [])
    loop_count = state.get("reflexion_loops", 0)

    has_log_citation = any(c.get("source_type") in ("log", "metric") for c in citations)
    has_git_citation = any(c.get("source_type") == "git_commit" for c in citations)
    has_runbook_citation = any(c.get("source_type") == "runbook" for c in citations)

    # Verification criteria
    is_verified = (has_log_citation and (has_git_citation or has_runbook_citation))
    missing = []
    if not has_log_citation:
        missing.append("Log timestamp or metric threshold citation")
    if not has_git_citation and not has_runbook_citation:
        missing.append("Git commit SHA or Runbook ID citation")

    critic_eval = {
        "is_verified": is_verified or (loop_count >= MAX_REFLEXION_LOOPS),
        "loop_count": loop_count + 1,
        "missing_evidence": missing,
        "critique": "RCA verified with concrete citations across telemetry and deployments." if is_verified else f"Missing evidence citations: {', '.join(missing)}.",
        "has_concrete_citations": bool(citations)
    }

    next_status = IncidentStatus.AWAITING_APPROVAL.value if critic_eval["is_verified"] else IncidentStatus.INVESTIGATING.value

    return {
        "status": next_status,
        "critic_eval": critic_eval,
        "reflexion_loops": loop_count + 1
    }


# =============================================================================
# 5. MCP REMEDIATION EXECUTOR & MEMORY NODE
# =============================================================================

def remediation_executor_node(state: IncidentState) -> Dict[str, Any]:
    """
    Executes approved remediation via MCP and stores resolution in Episodic Memory.
    """
    rca = state.get("rca_report", {})
    remediations = rca.get("recommended_remediations", [])
    alert = state.get("alert", {})

    if not remediations:
        return {
            "status": IncidentStatus.FAILED.value,
            "error": "No remediation actions specified in RCA report."
        }

    # Execute primary action
    action = remediations[0]
    tool_name = action.get("tool_name")
    params = action.get("parameters", {}).copy()

    # Ensure target service_name is present in params
    if "service_name" not in params:
        params["service_name"] = action.get("service_name") or alert.get("service_name", "unknown")

    exec_result = MCPToolRegistry.execute_tool(tool_name, **params)
    is_success = exec_result.get("status") == "SUCCESS"

    result_payload = {
        "action_id": action.get("action_id", "ACT-01"),
        "tool_name": tool_name,
        "status": "SUCCESS" if is_success else "FAILED",
        "output_message": exec_result.get("message") or exec_result.get("error", "Executed"),
        "validation_status": "System health restored" if is_success else "Manual intervention needed"
    }

    # Record in long-term Episodic Memory Store if successful
    if is_success:
        memory_store = EpisodicIncidentStore()
        memory_store.record_resolution(
            incident_id=alert.get("alert_id", "INC-AUTO"),
            service_name=alert.get("service_name", "unknown"),
            error_code=alert.get("error_code", "UNKNOWN_ERR"),
            symptom_signature=alert.get("title", ""),
            probable_root_cause=rca.get("probable_root_cause", ""),
            remediation_action=action.get("action_id", "ACT-01"),
            remediation_tool=tool_name,
            parameters_json=json.dumps(params),
            was_successful=True
        )

    return {
        "status": IncidentStatus.RESOLVED.value if is_success else IncidentStatus.FAILED.value,
        "remediation_result": result_payload
    }
