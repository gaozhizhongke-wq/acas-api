# ACAS v2 - Rollback Guide

This guide provides step-by-step procedures for rolling back ACAS v2 deployments in various failure scenarios.

---

## Rollback Scenarios

| Scenario | Symptoms | Rollback Method |
|----------|----------|-----------------|
| Bad deployment | API errors, broken features | Rollback Docker image tag |
| Database migration failure | Connection errors, schema mismatch | Restore from backup |
| Configuration error | Startup failures, auth errors | Revert environment variables |

---

## Quick Reference

```bash
# Immediate rollback (bad deployment)
docker compose down
docker tag ghcr.io/org/acas-v2:previous ghcr.io/org/acas-v2:latest
docker compose up -d

# Check health
curl http://localhost:8000/health

# View logs
docker compose logs -f api
```

---

## Step-by-Step Rollback Procedures

### Step 1: Identify the Issue

Before rolling back, identify the root cause:

#### Check Sentry for Errors

1. Open Sentry dashboard
2. Filter by `ACAS_ENVIRONMENT=production`
3. Look for spike in error rate after deployment

#### Check Loki Logs

Query recent errors in Grafana:

```logql
{job="acas-api"} |= "ERROR" | json | line_format "{{.timestamp}} {{.message}}"
```

Query for startup failures:

```logql
{job="acas-api"} |= "startup failed"
```

#### Check Prometheus Alerts

Review active alerts:

- `HighErrorRate` - API error rate > 5%
- `HighLatency` - P99 latency > 2s
- `DatabaseDown` - PostgreSQL disconnected
- `RedisDown` - Redis disconnected
- `InstanceDown` - API instance not responding

#### Common Indicators

| Indicator | Likely Cause |
|-----------|--------------|
| `ImportError` / `ModuleNotFoundError` | Bad deployment (code issue) |
| `OperationalError` / connection refused | Database issue |
| `AuthenticationError` | Configuration error |
| `ValidationError` | Schema migration mismatch |
| `RedisError` | Redis connectivity |
| HTTP 500 spike | Bad deployment |
| HTTP 401/403 spike | Auth configuration error |

---

### Step 2: Execute Rollback

#### Scenario A: Bad Code Deployment

**Symptoms:** Import errors, HTTP 500s, broken functionality

**Rollback procedure:**

```bash
# 1. Stop current deployment
docker compose down

# 2. Pull previous known-good image
# Option A: Use specific version tag
docker pull ghcr.io/your-org/acas-v2:v2.0.1

# Option B: Use previous SHA tag
docker pull ghcr.io/your-org/acas-v2:sha-abc123

# 3. Tag as latest (or update docker-compose.yml)
docker tag ghcr.io/your-org/acas-v2:v2.0.1 ghcr.io/your-org/acas-v2:latest

# 4. Redeploy
docker compose up -d

# 5. Verify health
curl -f http://localhost:8000/health

# 6. Check logs
docker compose logs -f api --tail=100
```

**Alternative: Update docker-compose.yml**

```yaml
services:
  api:
    image: ghcr.io/your-org/acas-v2:v2.0.1  # Pin to previous version
```

```bash
docker compose up -d
```

---

#### Scenario B: Database Migration Failure

**Symptoms:** Schema errors, `OperationalError`, column/table not found

**Rollback procedure:**

```bash
# 1. Check current migration status
docker compose exec api alembic current

# 2. Rollback to previous migration
docker compose exec api alembic downgrade -1

# 3. If downgrade fails, restore from backup (see Step 4)
```

**If migration caused data corruption:**

```bash
# 1. Stop API to prevent further damage
docker compose stop api

# 2. Restore from backup (see Step 4)

# 3. Start API with previous version
docker compose up -d
```

---

#### Scenario C: Configuration Error

**Symptoms:** Startup failures, authentication errors, CORS errors

**Common configuration issues:**

| Error | Missing/Misconfigured Var |
|-------|---------------------------|
| `SECRET_KEY not set` | `ACAS_SECRET_KEY` |
| `Database connection failed` | `ACAS_DB_URL` |
| `Redis connection failed` | `ACAS_REDIS_URL` |
| CORS errors | `ACAS_API_CORS_ORIGINS` |
| `Sentry initialization failed` | `ACAS_SENTRY_DSN` |

**Rollback procedure:**

```bash
# 1. Identify the misconfigured variable
docker compose logs api 2>&1 | grep -i "error\|failed\|invalid"

# 2. Fix environment variable
# Edit .env file or environment source
nano .env

# 3. Restart services
docker compose down
docker compose up -d

# 4. Verify
docker compose logs -f api --tail=50
curl http://localhost:8000/health
```

**Quick fixes for common errors:**

```bash
# Missing SECRET_KEY
ACAS_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
export ACAS_SECRET_KEY

# Wrong CORS origins
ACAS_API_CORS_ORIGINS=https://your-actual-domain.com

# Database URL format
ACAS_DB_URL=postgresql+psycopg://user:pass@host:5432/dbname
```

---

### Step 3: Verify Health

After any rollback, verify system health:

```bash
# Health endpoint
curl -f http://localhost:8000/health
# Expected: {"status": "healthy", ...}

# Metrics endpoint
curl http://localhost:8000/metrics | grep acas_database_connected
# Expected: acas_database_connected 1

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[].health'
# Expected: "up"

# Check recent logs
docker compose logs api --tail=100 | grep -i error
# Expected: No recent errors

# Test API functionality
curl http://localhost:8000/api/v1/health
```

**Health check script:**

```bash
#!/bin/bash
# health-check.sh

echo "Checking ACAS health..."

# Health endpoint
if curl -sf http://localhost:8000/health > /dev/null; then
    echo "✓ Health endpoint OK"
else
    echo "✗ Health endpoint FAILED"
    exit 1
fi

# Database
DB_STATUS=$(curl -s http://localhost:8000/health | jq -r '.database')
if [ "$DB_STATUS" = "connected" ]; then
    echo "✓ Database OK"
else
    echo "✗ Database FAILED"
    exit 1
fi

# Redis
REDIS_STATUS=$(curl -s http://localhost:8000/health | jq -r '.redis')
if [ "$REDIS_STATUS" = "connected" ]; then
    echo "✓ Redis OK"
else
    echo "✗ Redis FAILED"
    exit 1
fi

echo "All checks passed!"
```

---

### Step 4: Restore from Backup

If rollback requires data restoration:

#### PostgreSQL Restore

**From pg_dump backup:**

```bash
# 1. Stop API to prevent writes
docker compose stop api

# 2. Drop and recreate database
docker compose exec db psql -U acas -d postgres -c "DROP DATABASE acas;"
docker compose exec db psql -U acas -d postgres -c "CREATE DATABASE acas OWNER acas;"

# 3. Restore from backup
cat /backup/acas_2024-01-15.sql | docker compose exec -T db psql -U acas -d acas

# 4. Verify tables exist
docker compose exec db psql -U acas -d acas -c "\dt"

# 5. Restart API
docker compose start api
```

**From WAL archive (Point-in-Time Recovery):**

```bash
# 1. Stop PostgreSQL
docker compose stop db

# 2. Restore base backup
rm -rf /var/lib/postgresql/17/data/*
tar -xzf /backup/base/acas_base_2024-01-15.tar.gz -C /var/lib/postgresql/17/data/

# 3. Create recovery config
cat > /var/lib/postgresql/17/data/postgresql.conf << EOF
restore_command = 'cp /backup/wal_archive/%f %p'
recovery_target_time = '2024-01-15 10:30:00'
recovery_target_action = 'promote'
EOF

# 4. Start recovery
docker compose start db

# 5. Monitor recovery
docker compose logs -f db | grep "recovery"
```

#### Docker Volume Restore

```bash
# 1. Stop containers
docker compose down

# 2. Restore volumes
# Prometheus data
docker run --rm -v acas-v2_prometheus_data:/data -v /backup:/backup alpine \
  tar -xzf /backup/prometheus_data.tar.gz -C /data

# Grafana data
docker run --rm -v acas-v2_grafana_data:/data -v /backup:/backup alpine \
  tar -xzf /backup/grafana_data.tar.gz -C /data

# 3. Restart
docker compose up -d
```

---

### Step 5: Post-Rollback Actions

After successful rollback:

1. **Document the incident:**
   - What triggered the rollback
   - Root cause analysis
   - Steps taken to resolve
   - Timeline of events

2. **Update monitoring:**
   - Check Sentry for new errors
   - Review Prometheus metrics for anomalies
   - Update alert thresholds if needed

3. **Communicate:**
   - Notify team of rollback
   - Update status page if customer-facing
   - Schedule post-mortem if significant

4. **Plan fix:**
   - Identify what needs to be fixed
   - Create issue/ticket
   - Test fix in staging environment

---

## Backup Strategy

### PostgreSQL Backups

#### Daily pg_dump

```bash
#!/bin/bash
# backup-postgres.sh

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="/backup/postgres"
mkdir -p $BACKUP_DIR

# Full database dump
docker compose exec -T db pg_dump -U acas acas | gzip > $BACKUP_DIR/acas_$DATE.sql.gz

# Keep last 30 days
find $BACKUP_DIR -name "acas_*.sql.gz" -mtime +30 -delete

echo "Backup completed: acas_$DATE.sql.gz"
```

**Cron job:**

```cron
0 2 * * * /opt/acas/scripts/backup-postgres.sh >> /var/log/acas-backup.log 2>&1
```

#### Continuous WAL Archiving

**Enable in `postgresql.conf`:**

```ini
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /backup/wal_archive/%f && cp %p /backup/wal_archive/%f'
```

**For point-in-time recovery:**

```bash
# Create base backup
docker compose exec db pg_basebackup -U acas -D /backup/base/acas_$(date +%Y-%m-%d) -Ft -z -P
```

### Docker Volume Backups

```bash
#!/bin/bash
# backup-volumes.sh

DATE=$(date +%Y-%m-%d)
BACKUP_DIR="/backup/volumes"
mkdir -p $BACKUP_DIR

# Prometheus data
docker run --rm -v acas-v2_prometheus_data:/data -v $BACKUP_DIR:/backup alpine \
  tar -czf /backup/prometheus_$DATE.tar.gz -C /data .

# Grafana data
docker run --rm -v acas-v2_grafana_data:/data -v $BACKUP_DIR:/backup alpine \
  tar -czf /backup/grafana_$DATE.tar.gz -C /data .

# Database data (alternative to pg_dump)
docker run --rm -v acas-v2_postgres_data:/data -v $BACKUP_DIR:/backup alpine \
  tar -czf /backup/postgres_data_$DATE.tar.gz -C /data .

# Keep last 7 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

echo "Volume backups completed"
```

### Configuration Backup

All environment variables should be stored in:

- **HashiCorp Vault** - Recommended
- **AWS Secrets Manager** - For AWS deployments
- **Azure Key Vault** - For Azure deployments
- **1Password / Bitwarden** - For smaller setups

**Export for emergency recovery:**

```bash
# Export current config (store securely!)
docker compose config > /backup/acas-compose-config_$(date +%Y-%m-%d).yml
env | grep ACAS_ > /backup/acas-env_$(date +%Y-%m-%d).txt
```

---

## Emergency Contacts

| Role | Contact |
|------|---------|
| On-call engineer | [Configure in PagerDuty/OpsGenie] |
| Database admin | [Contact info] |
| Security team | [Contact info] |

---

## Rollback Checklist

- [ ] Issue identified (check Sentry, Loki, Prometheus)
- [ ] Rollback method determined
- [ ] Rollback executed
- [ ] Health check passed
- [ ] Logs verified (no errors)
- [ ] Team notified
- [ ] Incident documented
- [ ] Post-mortem scheduled

---

## Related Documentation

- [Production Deployment Guide](./production_deployment.md)
- [CI/CD Pipeline Documentation](../.github/workflows/ci.yml)
- [Alert Rules Configuration](../deploy/alert-rules.yml)
