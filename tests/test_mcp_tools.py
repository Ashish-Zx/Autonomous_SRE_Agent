"""
Unit Tests for MCP Server Tools & Boundaries (Module 5).
"""

from src.mcp_server.mcp_client import MCPToolRegistry


def test_query_service_logs():
    res = MCPToolRegistry.execute_tool("query_service_logs", service_name="order-service", limit=5)
    assert "logs" in res
    assert "formatted_telemetry" in res
    assert res["service_name"] == "order-service"


def test_get_service_metrics():
    res = MCPToolRegistry.execute_tool(
        "get_service_metrics",
        service_name="order-service",
        metric_name="db_connection_utilization",
        limit=5
    )
    assert "datapoints" in res
    assert res["metric_name"] == "db_connection_utilization"


def test_inspect_commit_diff():
    res = MCPToolRegistry.execute_tool(
        "inspect_commit_diff",
        service_name="order-service",
        commit_sha="b7e21a4"
    )
    assert res["commit_sha"] == "b7e21a4"
    assert "maximum-pool-size" in res["diff_patch"]


def test_remediation_tool_execution():
    res = MCPToolRegistry.execute_tool(
        "update_connection_pool_limit",
        service_name="order-service",
        max_connections=120
    )
    assert res["status"] == "SUCCESS"
    assert res["max_connections"] == 120

