"""
Episodic Incident Memory Store (Module 5).
Persists past resolved outages, symptom signatures, and proven remediation actions
across conversation threads in an episodic SQLite database.
Allows the triage agent to immediately recognize recurring outages.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.config import EPISODIC_MEMORY_DB_PATH


class EpisodicIncidentStore:
    """Cross-thread long-term memory store for historical incident resolutions."""

    def __init__(self, db_path: Path = EPISODIC_MEMORY_DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS episodic_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT NOT NULL,
            service_name TEXT NOT NULL,
            error_code TEXT NOT NULL,
            symptom_signature TEXT NOT NULL,
            probable_root_cause TEXT NOT NULL,
            remediation_action TEXT NOT NULL,
            remediation_tool TEXT NOT NULL,
            parameters_json TEXT NOT NULL,
            was_successful INTEGER NOT NULL,
            resolved_at TEXT NOT NULL
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_episodic_code ON episodic_incidents(service_name, error_code);")
        conn.commit()
        conn.close()

    def record_resolution(
        self,
        incident_id: str,
        service_name: str,
        error_code: str,
        symptom_signature: str,
        probable_root_cause: str,
        remediation_action: str,
        remediation_tool: str,
        parameters_json: str = "{}",
        was_successful: bool = True
    ):
        """Saves a verified, successful incident resolution to episodic memory."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO episodic_incidents (
            incident_id, service_name, error_code, symptom_signature,
            probable_root_cause, remediation_action, remediation_tool,
            parameters_json, was_successful, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            incident_id,
            service_name,
            error_code,
            symptom_signature,
            probable_root_cause,
            remediation_action,
            remediation_tool,
            parameters_json,
            1 if was_successful else 0,
            datetime.now(timezone.utc).isoformat()
        ))
        conn.commit()
        conn.close()

    def find_similar_resolutions(
        self,
        service_name: str,
        error_code: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Queries episodic memory for identical or related past outages."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
        SELECT incident_id, service_name, error_code, symptom_signature,
               probable_root_cause, remediation_action, remediation_tool,
               parameters_json, resolved_at
        FROM episodic_incidents
        WHERE service_name = ? OR error_code = ?
        ORDER BY id DESC LIMIT ?
        """, (service_name, error_code, limit))

        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
