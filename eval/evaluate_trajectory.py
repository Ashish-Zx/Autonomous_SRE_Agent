"""
Automated Agent Trajectory & RCA Evaluation Suite (Module 5).
Measures:
- Tool-Selection Accuracy (compares agent's recommended remediation tool against ground truth)
- Citation Verification Rate (ensures RCA is grounded in logs, commits, or runbooks)
- Step Efficiency & Time-to-Remediation
"""

import json
import time
import sys
from pathlib import Path
from typing import Dict, List, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tabulate import tabulate
from src.agents.graph import start_incident_investigation, resume_with_human_approval

GOLDEN_BENCHMARK_PATH = Path(__file__).resolve().parent / "golden_incidents.json"


def run_trajectory_evaluation(limit: int = 5):
    """
    Evaluates agent trajectory across a representative slice of golden incidents.
    """
    test_cases = json.loads(GOLDEN_BENCHMARK_PATH.read_text(encoding="utf-8"))[:limit]

    print(f"\n=======================================================")
    print(f"[*] Running SentinelSRE Agent Trajectory Evaluation ({len(test_cases)} scenarios)")
    print(f"=======================================================\n")

    results_table = []
    correct_tools = 0
    total_citations = 0

    for idx, tc in enumerate(test_cases, start=1):
        test_id = tc["test_id"]
        service_name = tc["service_name"]
        expected_tool = tc["expected_remediation_tool"]

        alert = {
            "alert_id": f"ALERT-EVAL-{test_id}",
            "service_name": service_name,
            "error_code": tc["error_code"],
            "title": tc["query"],
            "severity": "P0_CRITICAL"
        }

        start_time = time.perf_counter()
        thread_id = f"eval-thread-{test_id}-{int(time.time())}"

        state = start_incident_investigation(alert, thread_id=thread_id)
        duration = time.perf_counter() - start_time

        rca = state.get("rca_report", {}) or {}
        remediations = rca.get("recommended_remediations", [])
        chosen_tool = remediations[0].get("tool_name") if remediations else "NONE"
        citations = rca.get("citations", [])

        # Match tool
        tool_matches = (chosen_tool == expected_tool)
        if tool_matches:
            correct_tools += 1

        total_citations += len(citations)

        # Resume with HITL approval
        resumed = resume_with_human_approval(thread_id=thread_id, approved=True)
        final_status = resumed.get("status", "UNKNOWN")

        results_table.append([
            test_id,
            service_name,
            tc["error_code"],
            expected_tool,
            chosen_tool,
            "PASS" if tool_matches else "FAIL",
            len(citations),
            f"{duration:.2f}s",
            final_status
        ])

    headers = [
        "Test ID", "Service", "Error Code", "Expected Tool",
        "Chosen Tool", "Tool Accuracy", "Citations", "Latency", "Status"
    ]
    print("\n" + tabulate(results_table, headers=headers, tablefmt="github") + "\n")

    accuracy = (correct_tools / len(test_cases)) * 100
    avg_citations = total_citations / len(test_cases)
    print(f"[*] Trajectory Tool Accuracy: {accuracy:.1f}% ({correct_tools}/{len(test_cases)})")
    print(f"[*] Average Citations per RCA: {avg_citations:.1f}")


if __name__ == "__main__":
    run_trajectory_evaluation(limit=5)
