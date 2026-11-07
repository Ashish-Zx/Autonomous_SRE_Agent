"""
SentinelSRE: Live Incident War-Room Dashboard (Streamlit).
Allows an on-call engineer (or interviewer) to:
1. Trigger real simulated microservice outages or submit custom incident alerts.
2. Watch parallel multi-agent workers (Telemetry, Git, Runbook RAG) investigate concurrently.
3. Inspect the verified Root Cause Analysis (RCA) report with cited evidence.
4. Interact with the Human-in-the-Loop (HITL) approval gate to execute remediation over FastMCP.
5. Inspect the persistent cross-thread Episodic Memory Store.
"""

import sys
import time
import json
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from src.agents.graph import start_incident_investigation, resume_with_human_approval
from src.memory.episodic_store import EpisodicIncidentStore
from src.mcp_server.mcp_client import MCPToolRegistry

# Page Config
st.set_page_config(
    page_title="SentinelSRE — Autonomous Incident Triage War-Room",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
<style>
    .reportview-container { background-color: #0e1117; }
    .metric-card { background-color: #1a1c24; border-radius: 8px; padding: 15px; border-left: 4px solid #3b82f6; }
    .rca-box { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
    .badge-critical { background-color: #ef4444; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
    .badge-high { background-color: #f97316; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# Predefined Outage Scenarios
PRESET_SCENARIOS = {
    "1. Postgres Connection Pool Exhaustion (ERR_DB_POOL_9045)": {
        "service_name": "order-service",
        "error_code": "ERR_DB_POOL_9045",
        "title": "HikariPool Connection Timeout: Active connections 10/10, pending requests > 100",
        "severity": "P0_CRITICAL"
    },
    "2. Worker OOMKilled Termination (ERR_OOM_KILLED_137)": {
        "service_name": "payment-worker",
        "error_code": "ERR_OOM_KILLED_137",
        "title": "Container payment-worker in pod payment-worker-pod2 terminated with ExitCode 137 (OOMKilled)",
        "severity": "P0_CRITICAL"
    },
    "3. Redis Cache Stampede & 502 Bad Gateway (ERR_CACHE_STAMPEDE_502)": {
        "service_name": "catalog-service",
        "error_code": "ERR_CACHE_STAMPEDE_502",
        "title": "HTTP 502 Bad Gateway on /api/v1/catalog/flash_deal: Cache hit ratio dropped to 12%",
        "severity": "P0_CRITICAL"
    },
    "4. Ingress TLS Certificate Handshake Expiry (ERR_TLS_HANDSHAKE_409)": {
        "service_name": "api-gateway",
        "error_code": "ERR_TLS_HANDSHAKE_409",
        "title": "SSL_do_handshake() failed: certificate verify failed: certificate has expired",
        "severity": "P0_CRITICAL"
    },
    "5. SQL N+1 Query Regression & Latency Degradation (ERR_SQL_N_PLUS_ONE_8812)": {
        "service_name": "user-profile-service",
        "error_code": "ERR_SQL_N_PLUS_ONE_8812",
        "title": "p99 latency degraded from 120ms to 4,800ms: 1200 queries executed for 1 HTTP request",
        "severity": "P1_HIGH"
    }
}

# Sidebar
st.sidebar.title("🛡️ SentinelSRE Engine")
st.sidebar.caption("Autonomous AI SRE & Multi-Agent Incident Triage")
st.sidebar.markdown("---")

selected_preset = st.sidebar.selectbox("Simulate Outage Scenario:", list(PRESET_SCENARIOS.keys()))
scenario_data = PRESET_SCENARIOS[selected_preset]

st.sidebar.markdown("### Active Incident Alert")
service_name = st.sidebar.text_input("Service Name", scenario_data["service_name"])
error_code = st.sidebar.text_input("Error Code", scenario_data["error_code"])
severity = st.sidebar.selectbox("Severity", ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM"], index=0 if "P0" in scenario_data["severity"] else 1)
alert_title = st.sidebar.text_area("Alert Description", scenario_data["title"], height=100)

st.sidebar.markdown("---")
# Memory Store Viewer in Sidebar
episodic_store = EpisodicIncidentStore()
past_incidents = episodic_store.find_similar_resolutions(service_name=service_name, error_code=error_code, limit=3)
with st.sidebar.expander(f"🧠 Episodic Memory ({len(past_incidents)} past resolutions)", expanded=False):
    if past_incidents:
        for inc in past_incidents:
            st.markdown(f"**{inc['incident_id']}** ({inc['service_name']})")
            st.caption(f"Cause: {inc['probable_root_cause'][:120]}...")
            st.caption(f"Remediation: `{inc['remediation_tool']}`")
            st.markdown("---")
    else:
        st.write("No prior incident history recorded for this error signature.")


# Main App Title
st.title("🚨 SentinelSRE Incident War-Room")
st.markdown("Multi-agent concurrent investigation with **Two-Stage Hybrid RAG**, **FastMCP execution**, and **Human-in-the-Loop gating**.")

# Session State
if "incident_thread_id" not in st.session_state:
    st.session_state.incident_thread_id = None
if "current_investigation" not in st.session_state:
    st.session_state.current_investigation = None
if "remediation_complete" not in st.session_state:
    st.session_state.remediation_complete = False

# Action Buttons
col_start, col_reset = st.columns([3, 1])

with col_start:
    trigger_btn = st.button("🚀 Trigger Autonomous SRE Investigation", type="primary", use_container_width=True)

with col_reset:
    if st.button("🔄 Reset War-Room", use_container_width=True):
        st.session_state.incident_thread_id = None
        st.session_state.current_investigation = None
        st.session_state.remediation_complete = False
        st.rerun()

if trigger_btn:
    st.session_state.remediation_complete = False
    thread_id = f"incident-{int(time.time())}"
    st.session_state.incident_thread_id = thread_id

    alert_payload = {
        "alert_id": f"ALT-{int(time.time()) % 10000}",
        "service_name": service_name,
        "error_code": error_code,
        "title": alert_title,
        "severity": severity
    }

    with st.spinner("🤖 SentinelSRE Multi-Agent Graph executing parallel investigation..."):
        state = start_incident_investigation(alert_payload, thread_id=thread_id)
        st.session_state.current_investigation = state

# Render Investigation State
if st.session_state.current_investigation:
    inv_state = st.session_state.current_investigation
    rca = inv_state.get("rca_report", {}) or {}
    findings = inv_state.get("findings", [])
    critic = inv_state.get("critic_eval", {}) or {}
    status = inv_state.get("status")

    st.markdown("---")

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Investigation Status", status)
    with m2:
        st.metric("Parallel Findings", len(findings))
    with m3:
        st.metric("Evidence Citations", len(rca.get("citations", [])))
    with m4:
        st.metric("Critic Verified", "✅ YES" if critic.get("is_verified") else "⚠️ NO")

    # Parallel Worker Telemetry Breakdown
    st.subheader("🔍 Concurrent Specialist Evidence")
    w_cols = st.columns(3)

    telemetry_f = next((f for f in findings if f.get("worker_name") == "telemetry_worker"), None)
    git_f = next((f for f in findings if f.get("worker_name") == "git_worker"), None)
    runbook_f = next((f for f in findings if f.get("worker_name") == "runbook_worker"), None)

    with w_cols[0]:
        st.markdown("#### 📊 Telemetry & Logs")
        if telemetry_f:
            st.info(telemetry_f.get("summary"))
            st.caption(f"Confidence: {telemetry_f.get('confidence') * 100:.0f}%")
        else:
            st.write("Awaiting telemetry...")

    with w_cols[1]:
        st.markdown("#### 🐙 Git Deployment Diff")
        if git_f:
            st.warning(git_f.get("summary"))
            st.caption(f"Confidence: {git_f.get('confidence') * 100:.0f}%")
        else:
            st.write("Awaiting Git diff...")

    with w_cols[2]:
        st.markdown("#### 📚 Runbook Hybrid RAG")
        if runbook_f:
            st.success(runbook_f.get("summary"))
            st.caption(f"Confidence: {runbook_f.get('confidence') * 100:.0f}%")
        else:
            st.write("Awaiting RAG retrieval...")

    # Root Cause Analysis Report Card
    st.markdown("---")
    st.subheader("📋 Cited Root Cause Analysis (RCA)")
    
    with st.container():
        st.markdown(f"### {rca.get('summary', 'Root Cause Analysis')}")
        st.markdown(f"**Probable Cause:** {rca.get('probable_root_cause')}")
        st.markdown(f"**Blast Radius:** {rca.get('blast_radius')}")

        col_cit, col_time = st.columns([1, 1])
        with col_cit:
            st.markdown("#### 🔗 Concrete Evidence Citations")
            for c in rca.get("citations", []):
                st.markdown(f"- **[{c.get('source_type')}]** `{c.get('identifier')}`: *{c.get('snippet')}*")

        with col_time:
            st.markdown("#### ⏱️ Failure Timeline")
            for step in rca.get("failure_timeline", []):
                st.markdown(f"- {step}")

    # HUMAN-IN-THE-LOOP APPROVAL CARD
    st.markdown("---")
    st.subheader("🛑 Human-in-the-Loop Governance Gate")

    remediations = rca.get("recommended_remediations", [])
    if remediations and not st.session_state.remediation_complete and status == "AWAITING_APPROVAL":
        action = remediations[0]

        st.warning("⚠️ **Workflow Paused at Governance Gate**: Agent requires on-call engineer approval before executing remediation over FastMCP.")

        card_col1, card_col2 = st.columns([2, 1])
        with card_col1:
            st.markdown(f"**Target Action:** `{action.get('tool_name')}`")
            st.markdown(f"**Target Service:** `{action.get('service_name')}`")
            st.json(action.get("parameters", {}))
            if action.get("rollback_step"):
                st.caption(f"Safety Rollback: {action.get('rollback_step')}")

        with card_col2:
            st.markdown("#### Authorization")
            approve_btn = st.button("✅ Approve & Execute Remediation via MCP", type="primary", use_container_width=True)
            reject_btn = st.button("❌ Reject & Escalate", use_container_width=True)

            if approve_btn:
                with st.spinner("Executing remediation over FastMCP and updating episodic memory..."):
                    resumed_state = resume_with_human_approval(st.session_state.incident_thread_id, approved=True)
                    st.session_state.current_investigation = resumed_state
                    st.session_state.remediation_complete = True
                    st.rerun()

            if reject_btn:
                resumed_state = resume_with_human_approval(st.session_state.incident_thread_id, approved=False)
                st.session_state.current_investigation = resumed_state
                st.session_state.remediation_complete = True
                st.rerun()

    elif st.session_state.remediation_complete or status == "RESOLVED":
        rem_res = inv_state.get("remediation_result", {}) or {}
        st.success(f"🎉 **Incident Remediated Successfully!** Status: `{rem_res.get('status')}`")
        st.markdown(f"**Execution Output:** {rem_res.get('output_message')}")
        st.markdown(f"**Post-Remediation Check:** `{rem_res.get('validation_status')}`")
        st.info("🧠 This incident resolution signature has been saved into the Long-Term Episodic Memory Store for future triage.")
    elif status == "ESCALATED":
        st.error("🚨 Remediation was rejected by the on-call engineer. Incident escalated to human tier-3 response.")
