# Runbook: Rate Limiter Token Bucket Deadlock & Cascading 429s (ERR_RATE_LIMIT_STORM_429)

**Runbook ID:** RB-RATELIMIT-429  
**Target Services:** `auth-gateway`, `payment-gateway`, `partner-api`  
**Severity:** P1_HIGH  
**Author:** Edge Routing & Security Team  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_RATE_LIMIT_STORM_429`
- HTTP Status: `429 Too Many Requests`
- Log signature: `TokenBucketExhausted: Client IP 10.0.0.0/8 exceeded quota of 100 req/sec`
- Metric: `http_requests_429_total` jumps by 500x.
- Symptoms: Legitimate mobile and web clients receive 429 rejections indiscriminately; rate limiter keys locked in Redis.

---

## 2. Root Cause Triggers

1. **Missing Reverse Proxy Header Parsing:** A recent Nginx/Envoy config commit stopped reading `X-Forwarded-For` or `CF-Connecting-IP`, causing all internal clients to share the gateway's single internal IP address `10.0.0.1`.
2. **Missing Token Refill TTL:** Rate limiter script failed to replenish tokens due to an uncaught Redis Lua script syntax error.
3. **Aggressive Client Retry Loop:** Mobile client bug triggered immediate infinite retries without exponential backoff upon receiving any 4xx error.

---

## 3. Diagnostic Workflow

1. Query gateway logs for rate limit events and client IP distributions:
   ```bash
   mcp:query_service_logs(service_name="auth-gateway", severity="WARN", limit=50)
   ```
2. Check 429 request rate and rate limiter token metrics:
   ```bash
   mcp:get_service_metrics(service_name="auth-gateway", metric_name="rate_limit_rejections_per_sec")
   ```
3. Inspect recent commits to gateway configuration:
   ```bash
   mcp:get_recent_git_deployments(service_name="auth-gateway", limit=3)
   mcp:inspect_commit_diff(service_name="auth-gateway", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Reset Rate Limiter Keys & Adjust Threshold:**
   - Tool: `reset_rate_limit_counters`
   - Parameters: `{"service_name": "auth-gateway", "bucket_id": "global_client_bucket", "temporary_limit_factor": 3.0}`
2. **Rollback Faulty Reverse Proxy Deployment:**
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "auth-gateway", "target_commit": "<previous_stable_commit>"}`

### Post-Remediation Verification
- Confirm `rate_limit_rejections_per_sec` drops to baseline (< 2/sec).
- Confirm unique client IPs are properly resolved in request logs.
