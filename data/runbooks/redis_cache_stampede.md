# Runbook: Redis Cache Stampede & HTTP 502 Outage (ERR_CACHE_STAMPEDE_502)

**Runbook ID:** RB-REDIS-502  
**Target Services:** `catalog-service`, `checkout-api`, `pricing-service`  
**Severity:** P0_CRITICAL  
**Author:** Edge & API Performance Team  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_CACHE_STAMPEDE_502`
- HTTP Status: `502 Bad Gateway` returned by Nginx/Envoy API Gateway
- Redis metric: `redis_keyspace_hits` falls to zero for critical hot keys (`catalog:pricing:flash_deal`)
- Gateway log: `upstream prematurely closed connection while reading response header from upstream`
- Symptoms: Downstream database overwhelmed with 10,000 req/sec identical queries as cache TTL expires synchronously.

---

## 2. Root Cause Triggers

1. **Simultaneous Key Expiry:** Hot cache key expired with zero jitter, causing all incoming concurrent requests to hammer the backing database simultaneously (Thundering Herd / Cache Stampede).
2. **Cache Eviction Policy Exhaustion:** Redis `maxmemory-policy` evicted volatile keys under high memory pressure.
3. **Deployment without Cache Pre-Warming:** A recent deployment flushed the Redis database or changed the cache key schema without running a pre-warming script.

---

## 3. Diagnostic Workflow

1. Query API gateway and service logs for 502 errors and cache miss spikes:
   ```bash
   mcp:query_service_logs(service_name="catalog-service", severity="ERROR", limit=50)
   ```
2. Check Redis hit ratio and latency metrics:
   ```bash
   mcp:get_service_metrics(service_name="catalog-service", metric_name="cache_hit_ratio")
   mcp:get_service_metrics(service_name="catalog-service", metric_name="p99_latency_ms")
   ```
3. Inspect recent deployment history to check for cache schema or TTL adjustments:
   ```bash
   mcp:get_recent_git_deployments(service_name="catalog-service", limit=3)
   mcp:inspect_commit_diff(service_name="catalog-service", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Flush & Warm Cache:** Flush degraded keys and trigger pre-warming with distributed lock probabilistic early expiration:
   - Tool: `flush_and_warm_cache`
   - Parameters: `{"service_name": "catalog-service", "cache_tier": "redis_primary", "keyspace": "catalog:pricing"}`
2. **Temporary Replica Scale-Up:** Scale upstream service replicas to absorb database queue pressure:
   - Tool: `scale_service_replicas`
   - Parameters: `{"service_name": "catalog-service", "replica_count": 6}`

### Post-Remediation Verification
- Ensure `cache_hit_ratio` recovers to > 95%.
- Verify API Gateway HTTP 502 error rate drops to zero.

