# Runbook: N+1 SQL Query Regression & p99 Latency Degradation (ERR_SQL_N_PLUS_ONE_8812)

**Runbook ID:** RB-SQL-8812  
**Target Services:** `user-profile-service`, `search-api`, `order-service`  
**Severity:** P1_HIGH  
**Author:** Backend Architecture & Performance  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_SQL_N_PLUS_ONE_8812`
- Metric: `p99_latency_ms` spikes from 120ms baseline to > 4,800ms
- Log signature: `High query volume detected for endpoint /api/v1/orders: 1200 queries executed for 1 HTTP request`
- Database Metric: High read IOPS and query CPU saturation on RDS read replica.
- Symptoms: Cascading timeouts on downstream calling microservices; thread pool exhaustion.

---

## 2. Root Cause Triggers

1. **Lazy Loading Without Join Fetch:** Recent ORM migration or entity mapping change removed `@EntityGraph` or `joinedload(Order.items)` in SQLAlchemy/Hibernate, issuing 1 query for the parent order and N individual queries for each item.
2. **Missing Index on Foreign Key:** Commit added a new filter condition on an unindexed foreign key column (`user_id`, `tenant_id`).
3. **Loop Over ORM Objects:** Developer added a loop over a collection calling a DB query helper inside the loop instead of performing a batch SQL `WHERE IN (...)`.

---

## 3. Diagnostic Workflow

1. Query service logs for query execution counts and slow query logs:
   ```bash
   mcp:query_service_logs(service_name="user-profile-service", severity="WARN", limit=50)
   ```
2. Check p99 latency and database query count metrics:
   ```bash
   mcp:get_service_metrics(service_name="user-profile-service", metric_name="p99_latency_ms")
   mcp:get_service_metrics(service_name="user-profile-service", metric_name="db_queries_per_request")
   ```
3. Inspect the most recent deployment commit diff to pinpoint the ORM or repository changes:
   ```bash
   mcp:get_recent_git_deployments(service_name="user-profile-service", limit=3)
   mcp:inspect_commit_diff(service_name="user-profile-service", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Rollback Faulty Commit:** Revert to the prior deployment commit where batch fetching was properly configured:
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "user-profile-service", "target_commit": "<previous_stable_commit>"}`
2. **Scale Replicas (Temporary Buffer):** Increase service replicas to mitigate queue backup while rollback completes:
   - Tool: `scale_service_replicas`
   - Parameters: `{"service_name": "user-profile-service", "replica_count": 5}`

### Post-Remediation Verification
- Confirm `p99_latency_ms` drops back to < 150ms.
- Confirm `db_queries_per_request` returns to <= 3 queries.
