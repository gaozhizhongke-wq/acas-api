"""
ACAS v2 - Performance Optimization
Industrial deployment requirement: Database indexes and Redis caching
"""

from sqlalchemy import create_engine, text
from redis import Redis
import json
import os


def create_database_indexes():
    """Create database indexes for performance optimization"""

    # Read database URL from .env
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("ACAS_DB_URL="):
                db_url = line.strip().split("=", 1)[1]
                break

    # Create engine
    engine = create_engine(db_url)

    print("Creating database indexes...")

    indexes = [
        # Users table
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);",
        "CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC);",

        # API keys table
        "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash);",

        # Refresh tokens table
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens (token_hash);",
        "CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens (expires_at);",

        # Analysis history table
        "CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history (user_id);",
        "CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at ON analysis_history (created_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_analysis_history_brand ON analysis_history (brand);",

        # Forecast cache table
        "CREATE INDEX IF NOT EXISTS idx_forecast_cache_brand ON forecast_cache (brand);",
        "CREATE INDEX IF NOT EXISTS idx_forecast_cache_created_at ON forecast_cache (created_at DESC);",

        # News cache table
        "CREATE INDEX IF NOT EXISTS idx_news_cache_source ON news_cache (source);",
        "CREATE INDEX IF NOT EXISTS idx_news_cache_published_at ON news_cache (published_at DESC);",
    ]

    with engine.connect() as conn:
        for index_sql in indexes:
            try:
                conn.execute(text(index_sql))
                conn.commit()
                index_name = index_sql.split("idx_")[1].split(" ")[0]
                print(f"  ✓ Created index: idx_{index_name}")
            except Exception as e:
                print(f"  ✗ Failed to create index: {e}")

    print("Database indexes created successfully!")


def setup_redis_caching():
    """Setup Redis caching configuration"""

    # Read Redis URL from .env
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("ACAS_REDIS_URL="):
                redis_url = line.strip().split("=", 1)[1]
                break

    # Connect to Redis
    redis_client = Redis.from_url(redis_url)

    print("Setting up Redis caching...")

    # Configure Redis
    configs = {
        "maxmemory-policy": "allkeys-lru",  # Evict least recently used keys when memory full
        "maxmemory": "256mb",  # Limit memory usage
        "timeout": "300",  # Client timeout (seconds)
        "tcp-keepalive": "60",  # TCP keepalive
    }

    for key, value in configs.items():
        try:
            redis_client.config_set(key, value)
            print(f"  ✓ Set Redis config: {key} = {value}")
        except Exception as e:
            print(f"  ✗ Failed to set Redis config: {key} = {value}: {e}")

    # Create cache warming script
    warm_cache_script = """
import sys
sys.path.insert(0, 'src')

from core.database import db
from core.rate_limit import rate_limiter

# Warm up database connection
print("Warming up database connection...")
db.health_check()

# Warm up Redis connection
print("Warming up Redis connection...")
rate_limiter._redis.ping()

print("Cache warming completed!")
"""

    with open("scripts/warm_cache.py", "w") as f:
        f.write(warm_cache_script)

    print("  ✓ Created cache warming script: scripts/warm_cache.py")

    print("Redis caching setup completed!")


def optimize_postgresql_settings():
    """Optimize PostgreSQL settings for production"""

    print("Optimizing PostgreSQL settings...")

    # Recommended settings for production
    settings = {
        "shared_buffers": "256MB",  # 25% of RAM
        "effective_cache_size": "1GB",  # 75% of RAM
        "maintenance_work_mem": "64MB",
        "checkpoint_completion_target": "0.9",
        "wal_buffers": "16MB",
        "default_statistics_target": "100",
        "random_page_cost": "1.1",  # For SSD
        "effective_io_concurrency": "200",  # For SSD
        "work_mem": "4MB",
        "min_wal_size": "1GB",
        "max_wal_size": "4GB",
    }

    print("Recommended PostgreSQL settings (apply in postgresql.conf):")
    for key, value in settings.items():
        print(f"  {key} = {value}")

    print("\nTo apply these settings:")
    print("  1. Edit postgresql.conf")
    print("  2. Restart PostgreSQL")
    print("  3. Run: pg_ctl restart")


def create_performance_monitoring():
    """Create performance monitoring dashboard"""

    print("Creating performance monitoring configuration...")

    # Prometheus queries for monitoring
    prometheus_queries = {
        "request_rate": "rate(acas_requests_total[5m])",
        "error_rate": "rate(acas_requests_total{status=~'5..'}[5m])",
        "latency_p95": "histogram_quantile(0.95, rate(acas_request_duration_seconds_bucket[5m]))",
        "active_requests": "acas_requests_active",
        "database_connections": "pg_stat_activity_count",
        "redis_memory_usage": "redis_memory_used_bytes",
    }

    # Save to file
    import json
    with open("deploy/prometheus_queries.json", "w") as f:
        json.dump(prometheus_queries, f, indent=2)

    print("  ✓ Created Prometheus queries: deploy/prometheus_queries.json")

    # Grafana dashboard JSON
    grafana_dashboard = {
        "dashboard": {
            "title": "ACAS v2 Performance",
            "panels": [
                {"title": "Request Rate", "targets": [{"expr": prometheus_queries["request_rate"]}]},
                {"title": "Error Rate", "targets": [{"expr": prometheus_queries["error_rate"]}]},
                {"title": "Latency P95", "targets": [{"expr": prometheus_queries["latency_p95"]}]},
                {"title": "Active Requests", "targets": [{"expr": prometheus_queries["active_requests"]}]},
            ]
        }
    }

    with open("deploy/grafana_dashboard.json", "w") as f:
        json.dump(grafana_dashboard, f, indent=2)

    print("  ✓ Created Grafana dashboard: deploy/grafana_dashboard.json")

    print("Performance monitoring setup completed!")


if __name__ == "__main__":
    print("=" * 60)
    print("ACAS v2 Performance Optimization")
    print("=" * 60)

    print("\n[1/4] Creating database indexes...")
    create_database_indexes()

    print("\n[2/4] Setting up Redis caching...")
    setup_redis_caching()

    print("\n[3/4] Optimizing PostgreSQL settings...")
    optimize_postgresql_settings()

    print("\n[4/4] Creating performance monitoring...")
    create_performance_monitoring()

    print("\n" + "=" * 60)
    print("Performance optimization completed!")
    print("=" * 60)
