"""
Unit Tests for SentinelSRE FastAPI Microservice (Module 6 Bridge).
"""

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HEALTHY"
    assert "SentinelSRE" in data["service"]


def test_episodic_memory_history_endpoint():
    response = client.get("/api/memory/history")
    assert response.status_code == 200
    data = response.json()
    assert "incidents" in data
    assert isinstance(data["incidents"], list)


def test_triage_and_approval_workflow():
    alert_payload = {
        "alert_id": "ALT-API-TEST",
        "service_name": "order-service",
        "error_code": "ERR_DB_POOL_9045",
        "title": "HikariPool Connection Timeout API Test",
        "raw_message": "Timeout after 30000ms",
        "severity": "P0_CRITICAL"
    }

    # 1. Trigger Triage
    response = client.post("/api/incidents/triage", json=alert_payload)
    assert response.status_code == 200
    triage_data = response.json()
    assert "thread_id" in triage_data
    thread_id = triage_data["thread_id"]

    # 2. Get Thread Status
    status_resp = client.get(f"/api/incidents/{thread_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["thread_id"] == thread_id

    # 3. Approve via HITL endpoint (if paused)
    if status_data.get("is_paused_for_approval"):
        approve_resp = client.post(
            f"/api/incidents/{thread_id}/approve",
            json={"approved": True, "reason": "SRE authorized pool resize"}
        )
        assert approve_resp.status_code == 200
        approve_data = approve_resp.json()
        assert approve_data["status"] == "RESOLVED"

