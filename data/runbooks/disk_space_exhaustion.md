# Runbook: Ephemeral Disk Space Exhaustion (ERR_NO_SPACE_LEFT_ENOSPC)

**Runbook ID:** RB-DISK-9910  
**Target Services:** `file-upload-service`, `transcoder-service`, `log-aggregator`  
**Severity:** P0_CRITICAL  
**Author:** Node & Storage SRE  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_NO_SPACE_LEFT_ENOSPC`
- Log signature: `OSError: [Errno 28] No space left on device`
- Kubernetes pod status: `Evicted` with reason `DiskPressure: node has insufficient local disk space`
- Metric: `node_filesystem_free_bytes / node_filesystem_size_bytes < 0.05` (< 5% free space)
- Impact: Writes fail instantly, temporary tempfile creation raises uncaught exceptions, uploads fail.

---

## 2. Root Cause Triggers

1. **Unrotated Application Logs:** Debug logging was left enabled in production, creating multi-gigabyte `.log` files without `logrotate`.
2. **Orphaned Temporary Files:** File upload or image processing service failed to remove uploaded scratch artifacts in `/tmp` inside a `finally:` block.
3. **Core Dump Flooding:** Repeated segfaults generated numerous 2GB core dump files on the container root volume.

---

## 3. Diagnostic Workflow

1. Query service logs for `ENOSPC` or `No space left on device`:
   ```bash
   mcp:query_service_logs(service_name="file-upload-service", severity="ERROR", limit=30)
   ```
2. Check disk utilization metrics:
   ```bash
   mcp:get_service_metrics(service_name="file-upload-service", metric_name="disk_utilization_percent")
   ```
3. Inspect recent deployment history for changes to logging level or scratch directories:
   ```bash
   mcp:get_recent_git_deployments(service_name="file-upload-service", limit=3)
   mcp:inspect_commit_diff(service_name="file-upload-service", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Purge Scratch Disk and Rotate Logs:**
   - Tool: `cleanup_ephemeral_storage`
   - Parameters: `{"service_name": "file-upload-service", "target_path": "/tmp/uploads", "older_than_minutes": 15}`
2. **Rollback Over-Logging Deployment:**
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "file-upload-service", "target_commit": "<previous_stable_commit>"}`

### Post-Remediation Verification
- Confirm `disk_utilization_percent` drops below 60%.
- Ensure pod eviction alerts resolve.

