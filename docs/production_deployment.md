# ACAS v2 - Production Deployment Guide

This guide covers the complete production deployment process for ACAS v2.

---

## Table of Contents

1. [Environment Setup](#environment-setup)
2. [Deployment Methods](#deployment-methods)
3. [Security Checklist](#security-checklist)
4. [Health Check & Monitoring](#health-check--monitoring)
5. [CI/CD Pipeline](#cicd-pipeline)
6. [Production Tuning](#production-tuning)

---

## Environment Setup

### Required Environment Variables

Copy `.env.example` to `.env` and configure all variables before deployment.

#### Application Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_ENVIRONMENT` | Yes | `development` | Set to `production` for production deployments |
| `ACAS_DEBUG` | No | `false` | **NEVER** enable in production |

#### Security Settings

| Variable | Required | Description |
|----------|----------|-------------|
| `ACAS_SECRET_KEY` | **Yes** | 32+ character random string. Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ACAS_ENCRYPTION_KEY` | Optional | Fernet key for data encryption. Generate with: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

#### Database Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_DB_URL` | Yes | - | PostgreSQL connection URL: `postgresql+psycopg://user:pass@host:5432/dbname` |
| `ACAS_DB_POOL_SIZE` | No | `20` | Connection pool size |
| `ACAS_DB_MAX_OVERFLOW` | No | `40` | Max overflow connections |
| `ACAS_DB_SSL_MODE` | No | `prefer` | SSL mode: `disable`, `prefer`, `require`, `verify-full` |

#### Redis Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_REDIS_URL` | Yes | - | Redis connection URL: `redis://host:6379/0` |
| `ACAS_REDIS_PASSWORD` | Optional | - | Redis authentication password |

#### API Server Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_API_HOST` | No | `0.0.0.0` | Bind address |
| `ACAS_API_PORT` | No | `8000` | Listen port |
| `ACAS_API_WORKERS` | No | `4` | Uvicorn worker processes |
| `ACAS_API_CORS_ORIGINS` | **Yes** | - | Comma-separated allowed origins (e.g., `https://app.example.com,https://admin.example.com`) |
| `ACAS_API_CORS_ALLOW_CREDENTIALS` | No | `true` | Allow credentials in CORS requests |

#### Rate Limiting Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_RL_ENABLED` | No | `true` | Enable/disable rate limiting |
| `ACAS_RL_DEFAULT` | No | `100:60` | Default limit: `requests:seconds` |
| `ACAS_RL_LOGIN` | No | `5:300` | Login endpoint limit (5 attempts per 5 min) |
| `ACAS_RL_REGISTER` | No | `3:3600` | Registration limit (3 per hour) |

#### ML Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_ML_TIMESFM_ENABLED` | No | `true` | Enable TimesFM forecasting |
| `ACAS_ML_TIMESFM_MODEL_PATH` | Optional | - | Custom model path |
| `ACAS_ML_TIMESFM_CONTEXT_LENGTH` | No | `512` | Context window length |
| `ACAS_ML_TIMESFM_PREDICTION_HORIZON` | No | `96` | Forecast horizon |

#### Monitoring Settings

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ACAS_MON_LOG_LEVEL` | No | `INFO` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ACAS_MON_LOG_FORMAT` | No | `json` | Log format: `json` (production) or `text` (development) |
| `ACAS_MON_SENTRY_DSN` | Recommended | - | Sentry DSN for error tracking |
| `ACAS_MON_PROMETHEUS_ENABLED` | No | `true` | Enable Prometheus metrics |

#### External APIs (Optional)

| Variable | Description |
|----------|-------------|
| `NEWS_API_KEY` | NewsAPI key for premium news sources |
| `ALPHA_VANTAGE_KEY` | Alpha Vantage key for financial data |

---

### PostgreSQL 17 Setup

#### Installation

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql-17 postgresql-contrib-17

# macOS (Homebrew)
brew install postgresql@17
```

#### Database Creation

```sql
-- Connect as postgres user
sudo -u postgres psql

-- Create user and database
CREATE USER acas WITH ENCRYPTED PASSWORD 'your_secure_password';
CREATE DATABASE acas OWNER acas;
GRANT ALL PRIVILEGES ON DATABASE acas TO acas;

-- Enable extensions (optional)
\c acas
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For text search
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- For query analysis
```

#### Production Configuration

Edit `/etc/postgresql/17/main/postgresql.conf`:

```ini
# Connection settings
max_connections = 100
shared_buffers = 256MB
effective_cache_size = 768MB

# WAL for replication/backups
wal_level = replica
archive_mode = on
archive_command = 'cp %p /var/lib/postgresql/17/wal_archive/%f'

# Logging
log_destination = 'csvlog'
logging_collector = on
log_directory = 'pg_log'
log_min_duration_statement = 1000  # Log queries > 1s
```

#### SSL Configuration

```bash
# Generate self-signed cert (use real CA cert in production)
openssl req -new -x509 -days 365 -nodes \
  -text -out server.crt \
  -keyout server.key \
  -subj "/CN=your-domain.com"

chmod 600 server.key
chown postgres:postgres server.key server.crt

# postgresql.conf
ssl = on
ssl_cert_file = '/etc/postgresql/17/server.crt'
ssl_key_file = '/etc/postgresql/17/server.key'
```

---

### Redis 8 Setup

#### Installation

```bash
# Ubuntu/Debian
sudo apt install redis-server

# macOS (Homebrew)
brew install redis
```

#### Production Configuration

Edit `/etc/redis/redis.conf`:

```conf
# Persistence (AOF + RDB)
appendonly yes
appendfsync everysec
save 900 1
save 300 10
save 60 10000

# Memory
maxmemory 2gb
maxmemory-policy allkeys-lru

# Security
requirepass your_redis_password
bind 127.0.0.1

# Performance
tcp-backlog 511
tcp-keepalive 300
```

#### Start Redis

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Verify
redis-cli -a your_redis_password ping
```

---

### Docker/Compose Requirements

#### Docker Engine

- **Minimum version**: Docker Engine 24.0+
- **Recommended**: Docker Engine 26.0+

```bash
# Install Docker (Ubuntu)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

#### Docker Compose

- **Minimum version**: Docker Compose v2.20+
- **Recommended**: Docker Compose v2.30+

```bash
# Verify installation
docker compose version
```

#### System Resources

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 20 GB | 50+ GB SSD |

---

## Deployment Methods

### Method 1: Docker Compose (Recommended)

#### Prerequisites

1. Docker Engine 24.0+ installed
2. Docker Compose v2.20+ installed
3. Environment variables configured

#### Step 1: Configure Environment

```bash
# Create .env file
cp .env.example .env

# Edit with your values
nano .env
```

**Critical values to set:**

```bash
ACAS_ENVIRONMENT=production
ACAS_DEBUG=false
ACAS_SECRET_KEY=<generate-32-char-key>
ACAS_DB_URL=postgresql+psycopg://acas:your_password@db:5432/acas
ACAS_REDIS_URL=redis://redis:6379/0
ACAS_API_CORS_ORIGINS=https://your-domain.com
ACAS_SENTRY_DSN=https://xxx@sentry.io/xxx  # Optional but recommended
```

#### Step 2: Deploy with Compose

```bash
# Standard deployment (API + DB + Redis)
docker compose up -d

# With monitoring stack (Prometheus + Grafana + Loki)
docker compose --profile monitoring up -d

# Check status
docker compose ps
```

#### Step 3: Run Database Migrations

```bash
docker compose exec api alembic upgrade head
```

#### Step 4: Verify Deployment

```bash
# Health check
curl http://localhost:8000/health

# Metrics endpoint
curl http://localhost:8000/metrics
```

#### Exposing Services

For production, use a reverse proxy (nginx, Caddy, Traefik):

**Example nginx config:**

```nginx
upstream acas_api {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name api.your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    location / {
        proxy_pass http://acas_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

### Method 2: Manual Python Deployment

#### Prerequisites

- Python 3.11+
- PostgreSQL 17
- Redis 8
- Virtual environment

#### Step 1: Create Virtual Environment

```bash
python3.11 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate  # Windows
```

#### Step 2: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 3: Configure Environment

```bash
export ACAS_ENVIRONMENT=production
export ACAS_SECRET_KEY=<your-32-char-key>
export ACAS_DB_URL=postgresql+psycopg://acas:password@localhost:5432/acas
export ACAS_REDIS_URL=redis://localhost:6379/0
export ACAS_API_CORS_ORIGINS=https://your-domain.com
```

#### Step 4: Run Migrations

```bash
alembic upgrade head
```

#### Step 5: Start Server

```bash
# Single worker (development/testing)
python run.py

# Production with Gunicorn + Uvicorn workers
pip install gunicorn
gunicorn run:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

#### Step 6: Set Up Systemd Service

Create `/etc/systemd/system/acas.service`:

```ini
[Unit]
Description=ACAS v2 API Server
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=acas
Group=acas
WorkingDirectory=/opt/acas
Environment="PATH=/opt/acas/venv/bin"
EnvironmentFile=/opt/acas/.env
ExecStart=/opt/acas/venv/bin/gunicorn run:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable acas
sudo systemctl start acas
```

---

## Security Checklist

### 1. Secret Key Configuration

- [ ] `ACAS_SECRET_KEY` is set to a 32+ character random string
- [ ] `ACAS_SECRET_KEY` is stored in a secrets manager (Vault, AWS Secrets Manager, etc.)
- [ ] `ACAS_SECRET_KEY` is **never** committed to version control

**Generate secure key:**

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### 2. Error Tracking (Sentry)

- [ ] `ACAS_SENTRY_DSN` is configured
- [ ] Sentry project is created and DSN is obtained
- [ ] Error alerts are configured in Sentry

**Example DSN:**

```bash
ACAS_SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/1234567
```

### 3. CORS Configuration

- [ ] `ACAS_API_CORS_ORIGINS` is set to exact production domains
- [ ] Wildcards (`*`) are **not** used in production
- [ ] Credentials setting matches frontend requirements

**Correct format:**

```bash
ACAS_API_CORS_ORIGINS=https://app.your-domain.com,https://admin.your-domain.com
```

### 4. Database SSL

- [ ] PostgreSQL SSL is enabled
- [ ] `ACAS_DB_SSL_MODE` is set appropriately:
  - `require` - SSL required, no certificate verification
  - `verify-full` - SSL required with CA certificate verification (most secure)

```bash
ACAS_DB_URL=postgresql+psycopg://acas:password@db:5432/acas?sslmode=require
# or
ACAS_DB_SSL_MODE=require
```

### 5. Rate Limiting

- [ ] Rate limiting is enabled (`ACAS_RL_ENABLED=true`)
- [ ] Login brute force protection is configured
- [ ] Registration rate limits are set

**Production defaults:**

```bash
ACAS_RL_ENABLED=true
ACAS_RL_DEFAULT=100:60        # 100 requests per minute
ACAS_RL_LOGIN=5:300           # 5 login attempts per 5 minutes
ACAS_RL_REGISTER=3:3600       # 3 registrations per hour
```

### 6. Brute Force Protection

| Endpoint | Limit | Purpose |
|----------|-------|---------|
| `/auth/login` | 5 per 5 min | Prevent credential stuffing |
| `/auth/register` | 3 per hour | Prevent bot registration |

### 7. Logging Configuration

- [ ] Log format is JSON for production (`ACAS_MON_LOG_FORMAT=json`)
- [ ] Log level is appropriate (`INFO` recommended)
- [ ] Logs are shipped to aggregation system (Loki, ELK, etc.)

```bash
ACAS_MON_LOG_LEVEL=INFO
ACAS_MON_LOG_FORMAT=json
```

### 8. Network Security

- [ ] API is behind reverse proxy (nginx, Traefik, Caddy)
- [ ] HTTPS is enforced (TLS 1.2+)
- [ ] Security headers are configured:

```nginx
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

### 9. Container Security

- [ ] Containers run as non-root user
- [ ] `security_opt: no-new-privileges:true` is set
- [ ] Resource limits are configured:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

---

## Health Check & Monitoring

### Health Endpoint

The `/health` endpoint returns the overall system status:

```bash
curl http://localhost:8000/health
```

**Response (healthy):**

```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "version": "2.0.0"
}
```

**Response (degraded):**

```json
{
  "status": "degraded",
  "database": "connected",
  "redis": "disconnected",
  "version": "2.0.0"
}
```

### Metrics Endpoint

Prometheus metrics available at `/metrics`:

```bash
curl http://localhost:8000/metrics
```

**Key metrics exposed:**

| Metric | Type | Description |
|--------|------|-------------|
| `acas_requests_total` | Counter | Total HTTP requests |
| `acas_errors_total` | Counter | Total errors |
| `acas_request_duration_seconds` | Histogram | Request latency |
| `acas_database_connected` | Gauge | Database connection status (1/0) |
| `acas_redis_connected` | Gauge | Redis connection status (1/0) |

### Grafana Dashboards

After deploying the monitoring stack:

1. **Access Grafana**: `http://localhost:3000`
   - Default credentials: `admin` / `admin`
   - Change password on first login

2. **Add Prometheus data source**:
   - URL: `http://prometheus:9090`

3. **Add Loki data source** (for logs):
   - URL: `http://loki:3100`

4. **Recommended dashboards**:
   - ACAS API Overview (create custom)
   - PostgreSQL metrics
   - Redis metrics
   - Container metrics (cAdvisor)

**Example Grafana dashboard URLs after deployment:**

- Grafana: `http://your-server:3000`
- Prometheus: `http://your-server:9090`
- Loki: `http://your-server:3100`

### Loki Log Querying

Query logs in Grafana using LogQL:

**Recent errors:**

```logql
{job="acas-api"} |= "ERROR"
```

**HTTP 5xx responses:**

```logql
{job="acas-api"} |= "500"
```

**Rate-limited requests:**

```logql
{job="acas-api"} |= "rate limit exceeded"
```

**Log volume over time:**

```logql
sum(rate({job="acas-api"}[5m])) by (level)
```

---

## CI/CD Pipeline

### GitHub Actions Workflow

The project uses GitHub Actions for CI/CD with the following stages:

```yaml
# .github/workflows/ci.yml (existing)
jobs:
  test:
    # Unit tests with PostgreSQL + Redis services
  
  docker:
    # Build Docker image, push to GHCR
    # Deploy to production via SSH
```

### Deployment Flow

```
[Push to main] → [Run Tests] → [Build Docker Image] → [Push to GHCR] → [SSH Deploy] → [Smoke Test]
```

### Docker Registry (GHCR)

Images are pushed to GitHub Container Registry:

```bash
ghcr.io/your-org/acas-v2:latest
ghcr.io/your-org/acas-v2:v2.0.0
ghcr.io/your-org/acas-v2:sha-abc123
```

### SSH Deployment

The workflow uses SSH to deploy to production servers:

```yaml
# Example deployment step
- name: Deploy to Production
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.PRODUCTION_HOST }}
    username: ${{ secrets.PRODUCTION_USER }}
    key: ${{ secrets.PRODUCTION_SSH_KEY }}
    script: |
      cd /opt/acas
      docker compose pull
      docker compose up -d
      docker compose exec -T api curl -f http://localhost:8000/health
```

### Smoke Test Verification

After each deployment, the pipeline runs smoke tests:

1. **Health check**: `curl -f http://localhost:8000/health`
2. **Metrics check**: `curl http://localhost:8000/metrics`
3. **Database connectivity**: Verify via health response
4. **Redis connectivity**: Verify via health response

### Required GitHub Secrets

| Secret | Description |
|--------|-------------|
| `PRODUCTION_HOST` | Production server hostname/IP |
| `PRODUCTION_USER` | SSH username |
| `PRODUCTION_SSH_KEY` | Private SSH key |
| `GHCR_TOKEN` | GitHub token for container registry |

---

## Production Tuning

### Uvicorn Worker Count

**Formula:** `workers = (CPU_cores * 2) + 1`

```bash
# 4 CPU cores → 9 workers
ACAS_API_WORKERS=9

# 8 CPU cores → 17 workers
ACAS_API_WORKERS=17
```

**Memory consideration:**

Each worker consumes ~100-200MB RAM. Ensure total workers fit within available memory:

```
Workers = min((CPU_cores * 2 + 1), (Available_RAM_GB / 0.2))
```

### Database Connection Pool Sizing

**Pool size formula:**

```
pool_size = workers * 2
max_overflow = pool_size
```

```bash
# For 4 workers
ACAS_DB_POOL_SIZE=8
ACAS_DB_MAX_OVERFLOW=8

# For 9 workers
ACAS_DB_POOL_SIZE=18
ACAS_DB_MAX_OVERFLOW=18
```

**PostgreSQL max_connections must be greater than:**

```
total_pool_size = (pool_size + max_overflow) * num_instances
```

### Redis Connection Pool

Redis connections are managed by the Redis client library. Default pool size is typically 10-50 connections per worker.

### Rate Limit Settings

**Production recommendations:**

| Scenario | Default Rate | Login Rate | Register Rate |
|----------|--------------|------------|---------------|
| Low traffic | `100:60` | `5:300` | `3:3600` |
| Medium traffic | `200:60` | `10:300` | `5:3600` |
| High traffic | `500:60` | `20:300` | `10:3600` |

### Performance Tuning Checklist

- [ ] Worker count matches CPU cores
- [ ] Database pool size matches worker count
- [ ] PostgreSQL `max_connections` is sufficient
- [ ] Redis memory limit is configured
- [ ] Prometheus scrape interval is appropriate (default 5s for API)
- [ ] Log retention is configured (Loki/Grafana)

---

## Quick Reference

### Common Commands

```bash
# Deploy
docker compose up -d

# View logs
docker compose logs -f api

# Run migrations
docker compose exec api alembic upgrade head

# Rollback migration
docker compose exec api alembic downgrade -1

# Restart services
docker compose restart api

# Scale API workers
docker compose up -d --scale api=3

# Health check
curl http://localhost:8000/health

# Metrics
curl http://localhost:8000/metrics
```

### Useful Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/health` | Health check |
| `/metrics` | Prometheus metrics |
| `/docs` | OpenAPI documentation |
| `/redoc` | ReDoc documentation |
| `/openapi.json` | OpenAPI spec |

---

## Next Steps

1. Set up SSL certificates (Let's Encrypt recommended)
2. Configure Sentry alerts
3. Create Grafana dashboards
4. Set up database backups (see [Rollback Guide](./rollback_guide.md))
5. Configure log retention in Loki
