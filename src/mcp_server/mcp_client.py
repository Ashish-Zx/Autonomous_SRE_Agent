"""
MCP Client Adapter for LangGraph Multi-Agent Workflows.
Provides unified dispatching for both read-only diagnostic tools
and gated remediation actions, wrapping them as LangChain-compatible tools.
"""

from typing import Any, Dict, List, Optional
from langchain_core.tools import StructuredTool

from src.mcp_server.sre_mcp_server import (
    query_service_logs,
    get_service_metrics,
    get_recent_git_deployments,
    inspect_commit_diff,
    search_runbook_knowledge_base,
    rollback_service_deployment,
    update_connection_pool_limit,
    scale_service_replicas,
    flush_and_warm_cache,
    cleanup_ephemeral_storage,
    renew_tls_certificate,
    reset_rate_limit_counters,
)


class MCPToolRegistry:
    """Registry exposing all MCP tools for direct invocation and agent binding."""

    DIAGNOSTIC_TOOLS = {
        "query_service_logs": query_service_logs,
        "get_service_metrics": get_service_metrics,
        "get_recent_git_deployments": get_recent_git_deployments,
        "inspect_commit_diff": inspect_commit_diff,
        "search_runbook_knowledge_base": search_runbook_knowledge_base,
    }

    REMEDIATION_TOOLS = {
        "rollback_service_deployment": rollback_service_deployment,
        "update_connection_pool_limit": update_connection_pool_limit,
        "scale_service_replicas": scale_service_replicas,
        "flush_and_warm_cache": flush_and_warm_cache,
        "cleanup_ephemeral_storage": cleanup_ephemeral_storage,
        "renew_tls_certificate": renew_tls_certificate,
        "reset_rate_limit_counters": reset_rate_limit_counters,
    }

    @classmethod
    def execute_tool(cls, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Dispatches execution to the corresponding registered MCP tool."""
        if tool_name in cls.DIAGNOSTIC_TOOLS:
            return cls.DIAGNOSTIC_TOOLS[tool_name](**kwargs)
        elif tool_name in cls.REMEDIATION_TOOLS:
            return cls.REMEDIATION_TOOLS[tool_name](**kwargs)
        else:
            return {"status": "ERROR", "error": f"Unknown MCP tool '{tool_name}'"}

    @classmethod
    def get_langchain_diagnostic_tools(cls) -> List[StructuredTool]:
        """Wraps diagnostic tools as LangChain StructuredTools for agent binding."""
        return [
            StructuredTool.from_function(func=query_service_logs, name="query_service_logs", description="Query service logs by severity or error code"),
            StructuredTool.from_function(func=get_service_metrics, name="get_service_metrics", description="Get Prometheus/SQLite metrics for service"),
            StructuredTool.from_function(func=get_recent_git_deployments, name="get_recent_git_deployments", description="Get recent Git commits and deployments"),
            StructuredTool.from_function(func=inspect_commit_diff, name="inspect_commit_diff", description="Inspect Git diff patch for a commit SHA"),
            StructuredTool.from_function(func=search_runbook_knowledge_base, name="search_runbook_knowledge_base", description="Hybrid RAG search across engineering runbooks"),
        ]

    @classmethod
    def get_langchain_remediation_tools(cls) -> List[StructuredTool]:
        """Wraps gated remediation tools as LangChain StructuredTools."""
        return [
            StructuredTool.from_function(func=rollback_service_deployment, name="rollback_service_deployment", description="Rollback service to prior stable commit"),
            StructuredTool.from_function(func=update_connection_pool_limit, name="update_connection_pool_limit", description="Adjust database connection pool limit"),
            StructuredTool.from_function(func=scale_service_replicas, name="scale_service_replicas", description="Scale service pod replicas"),
            StructuredTool.from_function(func=flush_and_warm_cache, name="flush_and_warm_cache", description="Flush and pre-warm Redis cache"),
            StructuredTool.from_function(func=cleanup_ephemeral_storage, name="cleanup_ephemeral_storage", description="Clean scratch files to free disk space"),
            StructuredTool.from_function(func=renew_tls_certificate, name="renew_tls_certificate", description="Renew TLS certificate secrets"),
            StructuredTool.from_function(func=reset_rate_limit_counters, name="reset_rate_limit_counters", description="Reset rate limit counters"),
        ]

