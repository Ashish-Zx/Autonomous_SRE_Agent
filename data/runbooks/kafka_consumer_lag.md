# Runbook: Kafka Consumer Rebalance Storm & Lag Spike (ERR_KAFKA_REBALANCE_STORM)

**Runbook ID:** RB-KAFKA-7721  
**Target Services:** `event-processor`, `analytics-worker`, `notification-service`  
**Severity:** P1_HIGH  
**Author:** Streaming Data & Messaging SRE  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_KAFKA_REBALANCE_STORM`
- Log signature: `CommitFailedException: Offset commit cannot be completed since the consumer is not part of this consumer group`
- Broker log: `Heartbeat failure detected; member marked dead after max.poll.interval.ms exceeded`
- Metric: `kafka_consumergroup_lag` grows exponentially (> 250,000 unconsumed records).
- Symptoms: Downstream analytics and notifications delayed by hours; consumers repeatedly joining and leaving the consumer group.

---

## 2. Root Cause Triggers

1. **Slow Processing Exceeding `max.poll.interval.ms`:** A downstream blocking HTTP request or slow third-party API call took 5 minutes, exceeding the default 300,000ms poll timeout.
2. **Imbalanced Partition Assignment:** Recent deployment decreased partition count or spawned more consumer pods than topic partitions.
3. **Poison Pill Message:** An unparsable message payload causes a consumer thread to crash and trigger group rebalances repeatedly.

---

## 3. Diagnostic Workflow

1. Query consumer logs for rebalance warnings and poll timeout errors:
   ```bash
   mcp:query_service_logs(service_name="event-processor", severity="WARN", limit=50)
   ```
2. Check consumer group lag and rebalance rate metrics:
   ```bash
   mcp:get_service_metrics(service_name="event-processor", metric_name="consumer_lag_records")
   ```
3. Inspect recent deployment diffs for changes to `max.poll.interval.ms` or consumer handler logic:
   ```bash
   mcp:get_recent_git_deployments(service_name="event-processor", limit=3)
   mcp:inspect_commit_diff(service_name="event-processor", commit_sha="<commit_sha>")
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Increase Replicas & Reset Consumer Group Offsets:**
   - Tool: `scale_service_replicas`
   - Parameters: `{"service_name": "event-processor", "replica_count": 8}`
2. **Rollback Faulty Consumer Deployment:**
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "event-processor", "target_commit": "<previous_stable_commit>"}`

### Post-Remediation Verification
- Confirm `consumer_lag_records` steadily decreases to < 500 records.
- Confirm consumer group state transitions to `Stable`.
