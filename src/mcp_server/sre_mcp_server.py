"""
Custom Model Context Protocol (MCP) Server for SentinelSRE.
Separates:
- Read-Only Diagnostic Tools (Unrestricted access for investigator workers)
- Gated Write Remediation Tools (Protected by command guardrails and Human-in-the-Loop gating)
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from mcp.server.mcpserver import MCPServer

from src.config import (
    SIMULATOR_DB_PATH,
    RUNBOOKS_DIR,
    MAX_LOG_EXCERPT_LINES,
    MAX_COMMIT_DIFF_CHARS
)
from src.guardrails import validate_remediation_command, wrap_xml_telemetry
from src.rag.chunker import ParentChildMarkdownChunker
from src.rag.hybrid_retriever import HybridRAGRetriever
from src.rag.reranker import CrossEncoderReranker
from src.rag.crag_grader import CorrectiveRAGGrader

# Initialize MCPServer
mcp_app = MCPServer("sentinel_sre_mcp")

# Initialize RAG Pipeline for KB Search Tool
_rag_initialized = False
_retriever: Optional[HybridRAGRetriever] = None
_reranker: Optional[CrossEncoderReranker] = None
_grader: Optional[CorrectiveRAGGrader] = None


def get_rag_components():
    global _rag_initialized, _retriever, _reranker, _grader
    if not _rag_initialized:
        chunker = ParentChildMarkdownChunker()
        chunks = chunker.chunk_directory(RUNBOOKS_DIR)
        _retriever = HybridRAGRetriever()
        _retriever.index_chunks(chunks)
        _reranker = CrossEncoderReranker()
        _grader = CorrectiveRAGGrader()
        _rag_initialized = True
    return _retriever, _reranker, _grader


def _get_db():
    conn = sqlite3.connect(SIMULATOR_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# =============================================================================
# READ-ONLY DIAGNOSTIC TOOLS (Invoked freely by parallel investigation agents)
# =============================================================================

@mcp_app.tool()
def query_service_logs(
    service_name: str,
    severity: Optional[str] = None,
    error_code: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    Queries application and container logs for a target microservice.
    Filters by severity (e.g., ERROR, FATAL) or error_code (e.g., ERR_DB_POOL_9045).
    """
    limit = min(limit, MAX_LOG_EXCERPT_LINES)
    conn = _get_db()
    cursor = conn.cursor()

    query = "SELECT timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod FROM service_logs WHERE service_name = ?"
    params = [service_name]

    if severity:
        query += " AND level = ?"
        params.append(severity.upper())
    if error_code:
        query += " AND error_code = ?"
        params.append(error_code)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    logs = [dict(row) for row in rows]
    raw_text = "\n".join([f"[{r['timestamp']}] {r['level']} [{r['error_code'] or 'INFO'}] ({r['logger_name']}): {r['message']}" for r in logs])

    return {
        "service_name": service_name,
        "total_returned": len(logs),
        "logs": logs,
        "formatted_telemetry": wrap_xml_telemetry("service_logs", raw_text)
    }


@mcp_app.tool()
def get_service_metrics(
    service_name: str,
    metric_name: str,
    limit: int = 20
) -> Dict[str, Any]:
    """
    Retrieves recent time-series Prometheus/SQLite metrics for a target microservice.
    Examples: 'db_connection_utilization', 'memory_usage_mb', 'p99_latency_ms'.
    """
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT timestamp, service_name, metric_name, value, unit
    FROM service_metrics
    WHERE service_name = ? AND metric_name = ?
    ORDER BY id DESC LIMIT ?
    """, (service_name, metric_name, limit))

    rows = cursor.fetchall()
    conn.close()

    metrics = [dict(row) for row in rows][::-1]  # Chronological order
    metric_summary = "\n".join([f"{m['timestamp']}: {m['value']} {m['unit']}" for m in metrics])

    return {
        "service_name": service_name,
        "metric_name": metric_name,
        "datapoints": metrics,
        "formatted_telemetry": wrap_xml_telemetry("service_metrics", metric_summary)
    }


@mcp_app.tool()
def get_recent_git_deployments(service_name: str, limit: int = 5) -> Dict[str, Any]:
    """
    Returns deployment history and commit metadata for a target microservice.
    Identifies recent changes, author, and rollback target hashes.
    """
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT commit_sha, author, commit_message, deployed_at, environment, rollback_target_sha
    FROM git_deployments
    WHERE service_name = ?
    ORDER BY id DESC LIMIT ?
    """, (service_name, limit))

    rows = cursor.fetchall()
    conn.close()

    deployments = [dict(row) for row in rows]
    summary_text = "\n".join([
        f"Commit {d['commit_sha']} deployed at {d['deployed_at']} by {d['author']}: {d['commit_message']} (Rollback target: {d['rollback_target_sha']})"
        for d in deployments
    ])

    return {
        "service_name": service_name,
        "deployments": deployments,
        "formatted_telemetry": wrap_xml_telemetry("git_deployments", summary_text)
    }


@mcp_app.tool()
def inspect_commit_diff(service_name: str, commit_sha: str) -> Dict[str, Any]:
    """
    Inspects the exact Git diff patch introduced in a deployment commit.
    Critical for identifying configuration changes or logic bugs.
    """
    conn = _get_db()
    cursor = conn.cursor()

    cursor.execute("""
    SELECT commit_sha, author, commit_message, deployed_at, diff_patch, rollback_target_sha
    FROM git_deployments
    WHERE service_name = ? AND commit_sha = ?
    """, (service_name, commit_sha))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return {"error": f"Commit {commit_sha} not found for service {service_name}"}

    diff_data = dict(row)
    truncated_diff = diff_data["diff_patch"][:MAX_COMMIT_DIFF_CHARS]

    return {
        "service_name": service_name,
        "commit_sha": commit_sha,
        "author": diff_data["author"],
        "commit_message": diff_data["commit_message"],
        "rollback_target_sha": diff_data["rollback_target_sha"],
        "diff_patch": truncated_diff,
        "formatted_diff": wrap_xml_telemetry("git_diff", truncated_diff)
    }


@mcp_app.tool()
def search_runbook_knowledge_base(query: str, error_code: Optional[str] = None) -> Dict[str, Any]:
    """
    Two-Stage Hybrid RAG Runbook Search Tool.
    Searches engineering runbooks using BM25, FAISS, Cross-Encoder Reranking,
    and Corrective RAG grading.
    """
    retriever, reranker, grader = get_rag_components()
    raw_hits = retriever.search(query=query, top_k=6)
    reranked_hits = reranker.rerank(query=query, candidates=raw_hits, top_k=3)
    grade = grader.grade_retrieval(query=query, retrieved_docs=reranked_hits, error_code=error_code)

    top_doc = grade["documents"][0] if grade["documents"] else None
    content = top_doc.get("parent_content", "") if top_doc else "No relevant runbook located."

    return {
        "query": query,
        "error_code": error_code,
        "is_relevant": grade["is_relevant"],
        "crag_grade": grade["grade"],
        "top_runbook_title": top_doc.get("title") if top_doc else None,
        "matched_section": top_doc.get("header_path") if top_doc else None,
        "runbook_content": content,
        "web_fallback_used": grade["web_fallback_used"],
        "formatted_context": wrap_xml_telemetry("runbook_context", content)
    }


# =============================================================================
# GATED REMEDIATION WRITE TOOLS (Require Guardrail Check & HITL Approval)
# =============================================================================

@mcp_app.tool()
def rollback_service_deployment(service_name: str, target_commit: str) -> Dict[str, Any]:
    """
    Reverts service deployment to a designated stable Git commit SHA.
    Gated write tool executing infrastructure rollback.
    """
    params = {"service_name": service_name, "target_commit": target_commit}
    is_safe, reason = validate_remediation_command("rollback_service_deployment", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    # Simulate deployment rollback in SQLite
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        service_name,
        f"revert-{target_commit[:7]}",
        "SentinelSRE-Bot@corp.internal",
        f"Automated Rollback to stable commit {target_commit}",
        datetime.now(timezone.utc).isoformat(),
        "production",
        f"Rollback to commit {target_commit}",
        None
    ))
    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "action": "rollback_service_deployment",
        "service_name": service_name,
        "target_commit": target_commit,
        "message": f"Successfully rolled back {service_name} to commit {target_commit}. Container restart rolling update in progress."
    }


@mcp_app.tool()
def update_connection_pool_limit(service_name: str, max_connections: int) -> Dict[str, Any]:
    """
    Dynamically adjusts database connection pool ceiling for a target service.
    """
    params = {"service_name": service_name, "max_connections": max_connections}
    is_safe, reason = validate_remediation_command("update_connection_pool_limit", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    # Update metric baseline in SQLite to simulate recovery
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
    VALUES (?, ?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), service_name, "db_connection_utilization", 42.0, "percent"))
    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "action": "update_connection_pool_limit",
        "service_name": service_name,
        "max_connections": max_connections,
        "message": f"Updated {service_name} connection pool limit to {max_connections}. Pool utilization normalized."
    }


@mcp_app.tool()
def scale_service_replicas(service_name: str, replica_count: int) -> Dict[str, Any]:
    """
    Scales Kubernetes pod replica count horizontally for the target microservice.
    """
    params = {"service_name": service_name, "replica_count": replica_count}
    is_safe, reason = validate_remediation_command("scale_service_replicas", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    return {
        "status": "SUCCESS",
        "action": "scale_service_replicas",
        "service_name": service_name,
        "replica_count": replica_count,
        "message": f"Scaled {service_name} deployment to {replica_count} active replicas."
    }


@mcp_app.tool()
def flush_and_warm_cache(service_name: str, cache_tier: str, keyspace: str) -> Dict[str, Any]:
    """
    Flushes degraded hot keys and warms cache with distributed jittered TTL.
    """
    params = {"service_name": service_name, "cache_tier": cache_tier, "keyspace": keyspace}
    is_safe, reason = validate_remediation_command("flush_and_warm_cache", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
    VALUES (?, ?, ?, ?, ?)
    """, (datetime.now(timezone.utc).isoformat(), service_name, "cache_hit_ratio", 97.5, "percent"))
    conn.commit()
    conn.close()

    return {
        "status": "SUCCESS",
        "action": "flush_and_warm_cache",
        "service_name": service_name,
        "cache_tier": cache_tier,
        "keyspace": keyspace,
        "message": f"Cache keyspace '{keyspace}' on {cache_tier} warmed with probabilistic jittered TTL."
    }


@mcp_app.tool()
def cleanup_ephemeral_storage(service_name: str, target_path: str, older_than_minutes: int) -> Dict[str, Any]:
    """
    Safely purges scratch files, unrotated logs, and temp artifacts to relieve disk pressure.
    """
    params = {"service_name": service_name, "target_path": target_path, "older_than_minutes": older_than_minutes}
    is_safe, reason = validate_remediation_command("cleanup_ephemeral_storage", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    return {
        "status": "SUCCESS",
        "action": "cleanup_ephemeral_storage",
        "service_name": service_name,
        "target_path": target_path,
        "message": f"Purged scratch files older than {older_than_minutes}m in {target_path}. Disk space recovered."
    }


@mcp_app.tool()
def renew_tls_certificate(service_name: str, domain: str, cert_tier: str) -> Dict[str, Any]:
    """
    Renews TLS certificate secrets and triggers graceful ingress reload.
    """
    params = {"service_name": service_name, "domain": domain, "cert_tier": cert_tier}
    is_safe, reason = validate_remediation_command("renew_tls_certificate", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    return {
        "status": "SUCCESS",
        "action": "renew_tls_certificate",
        "service_name": service_name,
        "domain": domain,
        "message": f"Renewed TLS certificate for {domain} ({cert_tier}). Ingress controller secrets synchronized."
    }


@mcp_app.tool()
def reset_rate_limit_counters(service_name: str, bucket_id: str, temporary_limit_factor: float) -> Dict[str, Any]:
    """
    Resets deadlocked token bucket rate limit counters and applies temporary multiplier.
    """
    params = {"service_name": service_name, "bucket_id": bucket_id, "temporary_limit_factor": temporary_limit_factor}
    is_safe, reason = validate_remediation_command("reset_rate_limit_counters", params)
    if not is_safe:
        return {"status": "BLOCKED", "error": reason}

    return {
        "status": "SUCCESS",
        "action": "reset_rate_limit_counters",
        "service_name": service_name,
        "bucket_id": bucket_id,
        "message": f"Rate limiter bucket {bucket_id} reset with factor {temporary_limit_factor}x."
    }

