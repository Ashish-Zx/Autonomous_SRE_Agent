# Runbook: Ingress TLS Certificate Expiration & Handshake Failure (ERR_TLS_HANDSHAKE_409)

**Runbook ID:** RB-TLS-409  
**Target Services:** `api-gateway`, `auth-service`, `webhook-ingress`  
**Severity:** P0_CRITICAL  
**Author:** Security & Edge Networking SRE  

---

## 1. Symptom & Error Signatures

- Error code: `ERR_TLS_HANDSHAKE_409`
- Log signature: `SSL_do_handshake() failed (SSL: error:0A000086:SSL routines::certificate verify failed: certificate has expired)`
- Client symptom: Browser displays `NET::ERR_CERT_DATE_INVALID` or curl returns `curl: (60) SSL certificate problem: certificate has expired`
- Metric: Ingress HTTP request success rate drops from 99.9% to 0%.

---

## 2. Root Cause Triggers

1. **Cert-Manager Renewal Failure:** Automatic ACME / Let's Encrypt renewal loop failed due to rate limiting or DNS challenge timeout.
2. **Secret Synchronization Failure:** Kubernetes secret `api-tls-secret` was updated in the cluster, but the ingress controller pod did not reload the certificate into memory.
3. **Invalid Intermediate Chain:** Deployment pushed an incomplete certificate bundle missing the intermediate CA cert.

---

## 3. Diagnostic Workflow

1. Query gateway ingress logs for TLS errors:
   ```bash
   mcp:query_service_logs(service_name="api-gateway", severity="ERROR", limit=30)
   ```
2. Check certificate validity status and handshake error rate:
   ```bash
   mcp:get_service_metrics(service_name="api-gateway", metric_name="tls_handshake_failures")
   ```
3. Inspect recent deployment history or ingress config changes:
   ```bash
   mcp:get_recent_git_deployments(service_name="api-gateway", limit=3)
   ```

---

## 4. Remediation Procedures

### Immediate Mitigation (Automated)
1. **Rotate / Renew TLS Secret & Restart Ingress Pods:**
   - Tool: `renew_tls_certificate`
   - Parameters: `{"service_name": "api-gateway", "domain": "api.production.internal", "cert_tier": "wildcard"}`
2. **Fallback Gateway Traffic to Secondary Edge:**
   - Tool: `rollback_service_deployment`
   - Parameters: `{"service_name": "api-gateway", "target_commit": "<previous_known_good_cert_commit>"}`

### Post-Remediation Verification
- Test TLS handshake via openssl or curl.
- Verify `tls_handshake_failures` metric returns to 0.
