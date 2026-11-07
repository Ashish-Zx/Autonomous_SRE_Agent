# Postmortem: Outage INC-2024-08 (Order Service Database Connection Pool Exhaustion)

**Date:** 2024-08-15  
**Incident Commander:** Senior SRE Lead  
**Impact:** 42 minutes of elevated 500 errors on `/checkout` and `/orders` endpoints.  
**Root Cause:** Commit `b7e21a4` decreased `maximum-pool-size` from 150 to 10 in `application-prod.yml` inadvertently.  
**Resolution:** Reverted commit `b7e21a4` to `a1f9c32` and restarted pod replicas.  
**Lessons Learned:**
- Never commit hardcoded connection pool reductions without load testing.
- Added alert `ERR_DB_POOL_9045` with automated runbook RB-PG-9045.

