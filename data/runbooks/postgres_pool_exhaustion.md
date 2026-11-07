# Runbook: PostgreSQL Connection Pool Exhaustion (ERR_DB_POOL_9045)

**Runbook ID:** RB-PG-9045  
**Target Services:** `order-service`, `billing-service`, `inventory-service`  
**Severity:** P0_CRITICAL / P1_HIGH  
**Author:** SRE Database Reliability Team  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_DB_POOL_9045`
- Log signature: `FATAL: remaining connection slots are reserved for non-replication superuser connections`
- Client side error: `HikariPool-1 - Connection is not available, request timed out after 30000ms`
- Prometheus Metric: `pg_stat_activity_count >= 95% of max_connections`
- Symptoms: Incoming HTTP requests to order checkout fail with `500 Internal Server Error` or hang indefinitely.

---

## 2. Root Cause Triggers

1. **Undersized Pool Config in Git:** Recent commit altered `spring.datasource.hikari.maximum-pool-size` or Kubernetes env `DB_POOL_MAX` to an insufficient value or removed connection pooling entirely.
2. **Connection Leak in Application Code:** An unclosed transaction block or missing `defer db.Close()` / missing `try-with-resources` leaking active connections on slow queries.
3. **Database Lock Contention:** Long-running migration holding an `ACCESS EXCLUSIVE` lock on the `orders` or `accounts` table.

---

## 3. Diagnostic Workflow

1. Query service logs for `ERR_DB_POOL_9045` or `HikariPool` timeouts:
   ```bash
   mcp:query_service_logs(service_name="order-service", severity="ERROR", limit=50)
   ```
2. Check database connection pool metrics over the last 30 minutes:
   ```bash
   mcp:get_service_metrics(service_name="order-service", metric_name="db_connection_utilization")
   ```
3. Inspect recent Git deployments for database configuration changes:
   ```bash
   mcp:get_recent_git_deployments(service_name="order-service", limit=5)
   mcp:inspect_commit_diff(service_name="order-service", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Increase Pool Limit:** Update the service connection pool configuration if database headroom allows:
   - Tool: `update_connection_pool_limit`
   - Parameters: `{"service_name": "order-service", "max_connections": 150}`
2. **Rollback Faulty Deployment:** If caused by a recent commit changing connection pooling behavior:
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "order-service", "target_commit": "<previous_stable_commit>"}`

### Post-Remediation Verification
- Verify `db_connection_utilization` drops below 70%.
- Ensure HTTP 500 error rate drops to < 0.1%.

