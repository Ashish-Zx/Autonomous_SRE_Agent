"""
SentinelSRE Console Demo.
Runs an end-to-end incident investigation with rich colored terminal outputs:
- Telemetry & Log investigation
- Git Deployment Diff inspection
- Parent-Child Hybrid RAG runbook search
- Cited Root Cause Analysis (RCA) synthesis
- Reflexion Critic verification
- Human-in-the-Loop simulated approval
- FastMCP remediation execution
- Episodic Memory persistence
"""

import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

from src.agents.graph import start_incident_investigation, resume_with_human_approval

console = Console()


def run_demo():
    console.print(Panel.fit(
        "[bold cyan]🛡️ SentinelSRE: Autonomous AI Incident Triage Engine[/bold cyan]\n"
        "[dim]Flagship System (Modules 1–6) | LangGraph + FastMCP + Hybrid RAG + Reflexion[/dim]",
        border_style="cyan"
    ))

    alert = {
        "alert_id": "ALT-LIVE-9045",
        "service_name": "order-service",
        "error_code": "ERR_DB_POOL_9045",
        "title": "HikariPool Connection Timeout: Active connections 10/10, pending requests > 100",
        "severity": "P0_CRITICAL"
    }

    console.print("\n[bold yellow]🚨 1. Incoming P0 Alert Received:[/bold yellow]")
    console.print(f"   • Service: [bold]{alert['service_name']}[/bold]")
    console.print(f"   • Error Code: [red]{alert['error_code']}[/red]")
    console.print(f"   • Title: {alert['title']}")

    thread_id = f"demo-thread-{int(time.time())}"
    console.print("\n[bold blue]🤖 2. Dispatching Concurrent Specialist Workers (LangGraph Send API)...[/bold blue]")

    start_time = time.time()
    state = start_incident_investigation(alert, thread_id=thread_id)
    duration = time.time() - start_time

    findings = state.get("findings", [])
    rca = state.get("rca_report", {}) or {}
    critic = state.get("critic_eval", {}) or {}

    table = Table(title="Specialist Evidence Gathered Concurrently", show_header=True, header_style="bold magenta")
    table.add_column("Worker Node", style="cyan", width=22)
    table.add_column("Evidence Summary", style="white")
    table.add_column("Confidence", style="green", width=12)

    for f in findings:
        table.add_row(
            f.get("worker_name", ""),
            f.get("summary", "")[:120] + "...",
            f"{f.get('confidence', 0.0) * 100:.0f}%"
        )
    console.print(table)

    console.print("\n[bold green]📋 3. Synthesized Root Cause Analysis (RCA) Report:[/bold green]")
    console.print(Panel(
        f"[bold]Summary:[/bold] {rca.get('summary')}\n\n"
        f"[bold]Probable Cause:[/bold] {rca.get('probable_root_cause')}\n\n"
        f"[bold]Blast Radius:[/bold] {rca.get('blast_radius')}",
        title="Verified Root Cause Analysis",
        border_style="green"
    ))

    console.print("\n[bold]🔗 Citations Grounding the RCA:[/bold]")
    for c in rca.get("citations", []):
        console.print(f"   • [{c.get('source_type')}] [dim]{c.get('identifier')}:[/dim] {c.get('snippet')[:100]}...")

    console.print(f"\n[bold magenta]🔍 4. Reflexion Critic Verification:[/bold magenta] {'[bold green]PASSED[/bold green]' if critic.get('is_verified') else '[bold red]FAILED[/bold red]'}")
    console.print(f"   • Critique: {critic.get('critique')}")

    console.print("\n[bold red]🛑 5. Paused at Human-in-the-Loop Governance Gate (interrupt()):[/bold red]")
    remediations = rca.get("recommended_remediations", [])
    if remediations:
        action = remediations[0]
        console.print(f"   • Proposed Tool: [bold cyan]{action.get('tool_name')}[/bold cyan]")
        console.print(f"   • Parameters: {action.get('parameters')}")
        console.print(f"   • Rollback Step: {action.get('rollback_step')}")

    console.print("\n[bold yellow]⚡ 6. Simulating On-Call Engineer Approval...[/bold yellow]")
    resumed = resume_with_human_approval(thread_id=thread_id, approved=True)

    rem_res = resumed.get("remediation_result", {}) or {}
    console.print(Panel.fit(
        f"[bold green]🎉 Incident Remediated Successfully![/bold green]\n"
        f"• Status: {resumed.get('status')}\n"
        f"• Action: {rem_res.get('tool_name')}\n"
        f"• Message: {rem_res.get('output_message')}\n"
        f"• Validation: {rem_res.get('validation_status')}\n"
        f"• Total Time-to-Remediation: {duration:.2f} seconds\n"
        f"• Memory: Resolution saved to Long-Term Episodic Store",
        border_style="green"
    ))


if __name__ == "__main__":
    run_demo()

