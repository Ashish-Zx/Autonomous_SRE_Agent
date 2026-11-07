# Runbook: Worker Memory Leak & OOMKilled Termination (ERR_OOM_KILLED_137)

**Runbook ID:** RB-OOM-137  
**Target Services:** `payment-worker`, `notification-service`, `analytics-worker`  
**Severity:** P0_CRITICAL  
**Author:** Platform Infrastructure & Reliability  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_OOM_KILLED_137`
- Kubernetes Exit Code: `137 (Fatal error: Process terminated by SIGKILL, Out of Memory)`
- Container status: `OOMKilled: true, restartCount > 3`
- Metric: `container_memory_working_set_bytes` steadily climbs with a sawtooth pattern until reaching container limits (100%).
- Impact: Asynchronous payment processing stops; payment retry queues back up.

---

## 2. Root Cause Triggers

1. **Unbounded In-Memory Caching:** A recent release introduced an unevicted in-memory dictionary or static cache storing raw transaction JSON payloads.
2. **Bulk In-Memory Query:** An endpoint or worker pulled an unpaginated result set (e.g. `SELECT * FROM payment_audit_logs`) loading 500,000 records into memory.
3. **Cgroup Limit Misconfiguration:** A deployment reduced Kubernetes container memory limits below the baseline JVM/Node.js heap requirements.

---

## 3. Diagnostic Workflow

1. Query container termination logs and restart events:
   ```bash
   mcp:query_service_logs(service_name="payment-worker", severity="FATAL", limit=50)
   ```
2. Inspect time-series memory usage leading up to the crash:
   ```bash
   mcp:get_service_metrics(service_name="payment-worker", metric_name="memory_usage_mb")
   ```
3. Check recent Git deployment diffs for newly introduced cache maps or memory limit changes:
   ```bash
   mcp:get_recent_git_deployments(service_name="payment-worker", limit=3)
   mcp:inspect_commit_diff(service_name="payment-worker", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Rollback Bad Release:** Rollback to the previous stable release commit if memory leak was introduced in the latest release:
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "payment-worker", "target_commit": "<previous_stable_commit>"}`
2. **Horizontal Scaling / Restart:** Scale up worker replicas temporarily to distribute the queue load across pods while rollback proceeds:
   - Tool: `scale_service_replicas`
   - Parameters: `{"service_name": "payment-worker", "replica_count": 4}`

### Post-Remediation Verification
- Confirm container restarts stabilize at 0.
- Confirm `memory_usage_mb` plateaus below 65% of the memory ceiling.
