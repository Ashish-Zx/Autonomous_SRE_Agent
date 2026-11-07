"""
Realistic Telemetry & Git History Simulator for SentinelSRE.
Generates an operational SQLite database (data/sre_simulator.db) with:
1. Structured & Unstructured Application Logs
2. Time-series Prometheus-style Metrics
3. Git Deployment Commits & Diffs for Root Cause Tracing
"""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "sre_simulator.db"


def init_database():
    """Initializes schema for logs, metrics, and git deployments."""
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Logs Table
    cursor.execute("""
    CREATE TABLE service_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        service_name TEXT NOT NULL,
        level TEXT NOT NULL,
        error_code TEXT,
        logger_name TEXT NOT NULL,
        message TEXT NOT NULL,
        trace_id TEXT,
        host_pod TEXT NOT NULL
    );
    """)

    # 2. Time-Series Metrics Table
    cursor.execute("""
    CREATE TABLE service_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        service_name TEXT NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL NOT NULL,
        unit TEXT NOT NULL
    );
    """)

    # 3. Git Deployments Table
    cursor.execute("""
    CREATE TABLE git_deployments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        service_name TEXT NOT NULL,
        commit_sha TEXT NOT NULL UNIQUE,
        author TEXT NOT NULL,
        commit_message TEXT NOT NULL,
        deployed_at TEXT NOT NULL,
        environment TEXT NOT NULL,
        diff_patch TEXT NOT NULL,
        rollback_target_sha TEXT
    );
    """)

    # Indexes for fast agent retrieval
    cursor.execute("CREATE INDEX idx_logs_service_level ON service_logs(service_name, level);")
    cursor.execute("CREATE INDEX idx_logs_error_code ON service_logs(error_code);")
    cursor.execute("CREATE INDEX idx_metrics_service_name ON service_metrics(service_name, metric_name);")
    cursor.execute("CREATE INDEX idx_git_service ON git_deployments(service_name);")

    conn.commit()
    return conn


def seed_data(conn: sqlite3.Connection):
    cursor = conn.cursor()
    base_time = datetime.now(timezone.utc)

    # =========================================================================
    # SCENARIO 1: order-service (Postgres Pool Exhaustion ERR_DB_POOL_9045)
    # =========================================================================
    prev_sha_1 = "a1f9c32"
    bad_sha_1 = "b7e21a4"

    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "order-service",
        bad_sha_1,
        "alex.dev@corp.internal",
        "perf: optimize connection pool defaults for low-memory container",
        (base_time - timedelta(minutes=25)).isoformat(),
        "production",
        """--- a/src/main/resources/application-prod.yml
+++ b/src/main/resources/application-prod.yml
@@ -14,3 +14,3 @@ spring:
   datasource:
     hikari:
-      maximum-pool-size: 150
+      maximum-pool-size: 10
       connection-timeout: 30000""",
        prev_sha_1
    ))

    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "order-service",
        prev_sha_1,
        "ci-bot@corp.internal",
        "release: v2.3.9 stable release",
        (base_time - timedelta(days=2)).isoformat(),
        "production",
        "Initial stable deployment diff",
        None
    ))

    # Logs for order-service
    for i in range(15):
        t = (base_time - timedelta(minutes=20 - i)).isoformat()
        cursor.execute("""
        INSERT INTO service_logs (timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            t,
            "order-service",
            "ERROR",
            "ERR_DB_POOL_9045",
            "com.zaxxer.hikari.pool.HikariPool",
            f"HikariPool-1 - Connection is not available, request timed out after 30000ms. Active: 10/10, Pending requests: {45 + i * 5}",
            f"trace-ord-{1000 + i}",
            "order-service-7bb894-pod1"
        ))

    # Metrics for order-service
    for i in range(10):
        t = (base_time - timedelta(minutes=30 - (i * 3))).isoformat()
        utilization = 35.0 if i < 3 else (95.0 + i * 0.5)
        cursor.execute("""
        INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
        VALUES (?, ?, ?, ?, ?)
        """, (t, "order-service", "db_connection_utilization", min(utilization, 100.0), "percent"))

    # =========================================================================
    # SCENARIO 2: payment-worker (OOMKilled ERR_OOM_KILLED_137)
    # =========================================================================
    prev_sha_2 = "89ac231"
    bad_sha_2 = "c89d201"

    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "payment-worker",
        bad_sha_2,
        "sarah.fin@corp.internal",
        "feat: cache all processed transactions in static map for fast lookup",
        (base_time - timedelta(minutes=40)).isoformat(),
        "production",
        """--- a/workers/payment_processor.py
+++ b/workers/payment_processor.py
@@ -8,2 +8,4 @@
+PROCESSED_TXN_CACHE = {}  # In-memory unbounded map
 def process_payment(txn):
+    PROCESSED_TXN_CACHE[txn.id] = txn.to_json()  # Never cleared or evicted
     return execute_gateway_charge(txn)""",
        prev_sha_2
    ))

    cursor.execute("""
    INSERT INTO service_logs (timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (base_time - timedelta(minutes=10)).isoformat(),
        "payment-worker",
        "FATAL",
        "ERR_OOM_KILLED_137",
        "kubelet.pod_lifecycle",
        "Container payment-worker in pod payment-worker-5c79bf-pod2 was terminated: ExitCode 137 (OOMKilled). Memory limit 512Mi exceeded.",
        "trace-pay-9901",
        "k8s-node-worker-04"
    ))

    for i in range(8):
        t = (base_time - timedelta(minutes=40 - (i * 5))).isoformat()
        mem_mb = 180 + (i * 48)
        cursor.execute("""
        INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
        VALUES (?, ?, ?, ?, ?)
        """, (t, "payment-worker", "memory_usage_mb", float(mem_mb), "megabytes"))

    # =========================================================================
    # SCENARIO 3: catalog-service (Redis Stampede ERR_CACHE_STAMPEDE_502)
    # =========================================================================
    prev_sha_3 = "f44109a"
    bad_sha_3 = "e1a499b"

    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "catalog-service",
        bad_sha_3,
        "dave.edge@corp.internal",
        "chore: standardize redis cache TTL to midnight exact expiry without jitter",
        (base_time - timedelta(minutes=15)).isoformat(),
        "production",
        """--- a/config/cache.py
+++ b/config/cache.py
@@ -10,2 +10,2 @@
-DEFAULT_TTL_SEC = 3600 + random.randint(0, 300) # Jittered
+DEFAULT_TTL_SEC = 3600 # Static synchronous expiry""",
        prev_sha_3
    ))

    cursor.execute("""
    INSERT INTO service_logs (timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (base_time - timedelta(minutes=5)).isoformat(),
        "catalog-service",
        "ERROR",
        "ERR_CACHE_STAMPEDE_502",
        "nginx.ingress",
        "upstream prematurely closed connection while reading response header from upstream: 502 Bad Gateway on /api/v1/catalog/flash_deal",
        "trace-cat-4412",
        "ingress-controller-88"
    ))

    for i in range(6):
        t = (base_time - timedelta(minutes=15 - (i * 2))).isoformat()
        hit_ratio = 98.0 if i < 3 else 12.0
        cursor.execute("""
        INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
        VALUES (?, ?, ?, ?, ?)
        """, (t, "catalog-service", "cache_hit_ratio", float(hit_ratio), "percent"))

    # =========================================================================
    # SCENARIO 4: api-gateway (TLS Certificate Handshake ERR_TLS_HANDSHAKE_409)
    # =========================================================================
    bad_sha_4 = "f338b12"
    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "api-gateway",
        bad_sha_4,
        "jordan.ops@corp.internal",
        "ci: switch certbot renewal hook to custom shell script",
        (base_time - timedelta(hours=3)).isoformat(),
        "production",
        """--- a/infra/certs.sh
+++ b/infra/certs.sh
@@ -1,2 +1,2 @@
-certbot renew --post-hook "kubectl rollout restart deployment/api-gateway"
+certbot renew --dry-run""",
        "c41991a"
    ))

    cursor.execute("""
    INSERT INTO service_logs (timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (base_time - timedelta(minutes=12)).isoformat(),
        "api-gateway",
        "ERROR",
        "ERR_TLS_HANDSHAKE_409",
        "openresty.ssl",
        "SSL_do_handshake() failed (SSL: error:0A000086:SSL routines::certificate verify failed: certificate has expired for domain api.production.internal)",
        "trace-ssl-9011",
        "api-gateway-edge-01"
    ))

    # =========================================================================
    # SCENARIO 5: user-profile-service (N+1 Query Regression ERR_SQL_N_PLUS_ONE_8812)
    # =========================================================================
    bad_sha_5 = "d42a981"
    cursor.execute("""
    INSERT INTO git_deployments (service_name, commit_sha, author, commit_message, deployed_at, environment, diff_patch, rollback_target_sha)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        "user-profile-service",
        bad_sha_5,
        "priya.eng@corp.internal",
        "feat: render user achievement badges in profile header",
        (base_time - timedelta(minutes=35)).isoformat(),
        "production",
        """--- a/services/user_service.py
+++ b/services/user_service.py
@@ -25,2 +25,4 @@ def get_user_profile(user_id):
     user = db.query(User).filter_by(id=user_id).first()
+    for badge in user.badges: # N+1 query loop: 1 query per badge
+        badge.details = db.query(BadgeDetail).filter_by(badge_id=badge.id).first()
     return user""",
        "88e31bf"
    ))

    cursor.execute("""
    INSERT INTO service_logs (timestamp, service_name, level, error_code, logger_name, message, trace_id, host_pod)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        (base_time - timedelta(minutes=8)).isoformat(),
        "user-profile-service",
        "WARN",
        "ERR_SQL_N_PLUS_ONE_8812",
        "sqlalchemy.engine.Engine",
        "High query volume detected for endpoint /api/v1/profile: 1200 queries executed for 1 HTTP request. p99 latency threshold exceeded.",
        "trace-usr-7711",
        "user-profile-service-589"
    ))

    for i in range(5):
        t = (base_time - timedelta(minutes=25 - (i * 5))).isoformat()
        latency = 115.0 if i < 2 else (3800.0 + i * 250)
        cursor.execute("""
        INSERT INTO service_metrics (timestamp, service_name, metric_name, value, unit)
        VALUES (?, ?, ?, ?, ?)
        """, (t, "user-profile-service", "p99_latency_ms", float(latency), "milliseconds"))

    conn.commit()


if __name__ == "__main__":
    print(f"[*] Seeding SentinelSRE telemetry sandbox database at {DB_PATH}...")
    connection = init_database()
    seed_data(connection)
    connection.close()
    print("[+] Database successfully seeded with 5 realistic outage scenarios, metrics, and git diffs!")
