"""
LangGraph Multi-Agent State Machine for SentinelSRE (Module 5).
Features:
- Map-Reduce Parallel Execution via LangGraph `Send` API
- State Reducer combining findings from Telemetry, Git, and Runbook workers
- Reflexion Critic Verification Loop
- Human-in-the-Loop (`interrupt_before=['remediation_executor']`) approval gate
- Checkpointing for resilient pause/resume
"""

from typing import Dict, List, Any, Union
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver

from src.agents.nodes import (
    IncidentState,
    triage_node,
    telemetry_worker_node,
    git_worker_node,
    runbook_worker_node,
    rca_synthesizer_node,
    critic_node,
    remediation_executor_node
)
from src.schemas import IncidentStatus


def dispatch_workers(state: IncidentState) -> List[Send]:
    """
    Map-Reduce Fan-Out: Dispatches parallel specialist workers using the Send API.
    """
    if state.get("status") == IncidentStatus.FAILED.value:
        return []

    return [
        Send("telemetry_worker", state),
        Send("git_worker", state),
        Send("runbook_worker", state),
    ]


def critic_conditional_edge(state: IncidentState) -> str:
    """
    Reflexion Router:
    - If verified, proceeds to remediation_executor (paused at Human-in-the-Loop gate).
    - If deficient and under max loops, loops back to parallel workers.
    - Otherwise proceeds to remediation_executor.
    """
    critic_eval = state.get("critic_eval", {})
    is_verified = critic_eval.get("is_verified", False)
    loops = state.get("reflexion_loops", 0)

    if is_verified or loops >= 2:
        return "remediation_executor"
    return "triage"  # Loop back for additional worker evidence collection


def build_sre_graph(checkpointer=None):
    """Constructs and compiles the SentinelSRE LangGraph multi-agent system."""
    builder = StateGraph(IncidentState)

    # 1. Add Agent Nodes
    builder.add_node("triage", triage_node)
    builder.add_node("telemetry_worker", telemetry_worker_node)
    builder.add_node("git_worker", git_worker_node)
    builder.add_node("runbook_worker", runbook_worker_node)
    builder.add_node("rca_synthesizer", rca_synthesizer_node)
    builder.add_node("critic", critic_node)
    builder.add_node("remediation_executor", remediation_executor_node)

    # 2. Add Graph Edges & Parallel Fan-Out
    builder.add_edge(START, "triage")

    # Parallel Fan-Out via Send API
    builder.add_conditional_edges("triage", dispatch_workers, ["telemetry_worker", "git_worker", "runbook_worker", END])

    # Fan-In (Reduce): All 3 workers feed into RCA Synthesizer
    builder.add_edge("telemetry_worker", "rca_synthesizer")
    builder.add_edge("git_worker", "rca_synthesizer")
    builder.add_edge("runbook_worker", "rca_synthesizer")

    # Synthesizer -> Critic
    builder.add_edge("rca_synthesizer", "critic")

    # Critic -> Reflexion Loop OR Remediation Executor
    builder.add_conditional_edges("critic", critic_conditional_edge, ["triage", "remediation_executor"])

    # Executor -> END
    builder.add_edge("remediation_executor", END)

    # 3. Compile with Human-in-the-Loop Interrupt Gate
    # Graph execution will pause immediately before executing remediation_executor!
    app_checkpointer = checkpointer or MemorySaver()
    app = builder.compile(
        checkpointer=app_checkpointer,
        interrupt_before=["remediation_executor"]
    )

    return app


# Shared singleton instance
_checkpointer = MemorySaver()
sre_agent_app = build_sre_graph(checkpointer=_checkpointer)


def start_incident_investigation(alert: Dict[str, Any], thread_id: str) -> Dict[str, Any]:
    """
    Initiates parallel investigation for an alert.
    Pauses before remediation_executor at the Human-in-the-Loop gate.
    """
    initial_state: IncidentState = {
        "alert": alert,
        "status": IncidentStatus.DETECTED.value,
        "query": alert.get("title", ""),
        "similar_past_incidents": [],
        "findings": [],
        "rca_report": None,
        "critic_eval": None,
        "reflexion_loops": 0,
        "human_approval": None,
        "remediation_result": None,
        "error": None
    }

    config = {"configurable": {"thread_id": thread_id}}
    final_state = None

    # Stream execution until interrupt
    for event in sre_agent_app.stream(initial_state, config=config):
        # Captures state transitions
        for node_name, state_update in event.items():
            final_state = state_update

    # Fetch current paused state from checkpointer
    current_state = sre_agent_app.get_state(config)
    return current_state.values


def resume_with_human_approval(thread_id: str, approved: bool) -> Dict[str, Any]:
    """
    Resumes graph execution from the Human-in-the-Loop interrupt gate.
    If approved, executes remediation via MCP. If rejected, cancels execution.
    """
    config = {"configurable": {"thread_id": thread_id}}
    current_state = sre_agent_app.get_state(config)

    if not current_state or not current_state.next:
        return {"status": "NO_ACTIVE_INTERRUPT", "error": "No workflow paused for this thread_id"}

    if not approved:
        sre_agent_app.update_state(
            config,
            {"status": IncidentStatus.ESCALATED.value, "human_approval": {"approved": False, "reason": "Rejected by On-Call SRE"}}
        )
        return sre_agent_app.get_state(config).values

    # Resume by passing None to continue execution into remediation_executor
    for event in sre_agent_app.stream(None, config=config):
        pass

    resumed_state = sre_agent_app.get_state(config)
    return resumed_state.values
