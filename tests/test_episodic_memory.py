"""
Unit Tests for Long-Term Episodic Memory Store (Module 5).
"""

import tempfile
from pathlib import Path
from src.memory.episodic_store import EpisodicIncidentStore


def test_episodic_memory_write_and_recall():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_episodic.db"
        store = EpisodicIncidentStore(db_path=test_db)

        # Record resolution
        store.record_resolution(
            incident_id="INC-UNIT-TEST",
            service_name="payment-worker",
            error_code="ERR_OOM_KILLED_137",
            symptom_signature="Container terminated exit code 137",
            probable_root_cause="Unbounded transaction cache leak in v2.4.1",
            remediation_action="ACT-ROLLBACK",
            remediation_tool="rollback_service_deployment",
            parameters_json='{"service_name": "payment-worker", "target_commit": "89ac231"}',
            was_successful=True
        )

        # Recall
        results = store.find_similar_resolutions("payment-worker", "ERR_OOM_KILLED_137")
        assert len(results) == 1
        rec = results[0]
        assert rec["incident_id"] == "INC-UNIT-TEST"
        assert rec["remediation_tool"] == "rollback_service_deployment"
