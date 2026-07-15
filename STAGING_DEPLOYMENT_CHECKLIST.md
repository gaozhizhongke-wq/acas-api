# ACAS v2 Staging Deployment Checklist

Use this checklist before deploying to staging environment.

## Pre-Deployment

### 1. Code Review
- [ ] All codes changes reviewed and approved
- [ ] Unit tests passing (76 tests)
- [ ] Integration tests passing
- [ ] Security scan completed

### 2. Configuration
- [ ] `.env.staging` file created with secure values
- [ ] `ACAS_SECRET_KEY` changed from default (min 32 chars)
- [ ] Database credentials configured
- [ ] Redis password set (if required)
- [ ] CORS origins configured for test clients
- [ ] Rate limiting configured appropriately for testing

### 3. Dependencies
- [ ] Python 3.11+ installed
- [ ] PostgreSQL 16+ installed and running
- [ ] Redis 7+ installed and running
- [ ] All Python dependencies installed (`pip install -r requirements.txt`)
- [ ] Optional: Transformers model downloaded (for sentiment analysis)
- [ ] Optional: Prophet installed (`pip install prophet`)
- [ ] Optional: PyTorch installed (`pip install torch`)

### 4. Database
- [ ] Database created (`acas_staging`)
- [ ] Migrations ready to run (`alembic upgrade head`)
- [ ] Database user has proper permissions
- [ ] Backup of existing data (if applicable)

## Deployment

### 5. Docker Deployment (Recommended)
```bash
# 1. Build image
docker-compose -f docker-compose.staging.yml build

# 2. Start services
docker-compose -f docker-compose.staging.yml up -d

# 3. Run migrations
docker-compose -f docker-compose.staging.yml exec api alembic upgrade head

# 4. Create admin user
curl -X POST <http://localhost:8000/auth/register> \\
  -H "Content-Type: application/json" \\
  -d '{"email":"admin@acas-staging.com","password":"AdminPassword123!","name":"Admin"}'

# 5. Check health
curl <http://localhost:8000/health>
```

### 6. Manual Deployment
```bash
# 1. Set environment
export $(cat .env.staging | xargs)

# 2. Run migrations
alembic upgrade head

# 3. Start API
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Post-Deployment Verification

### 7. Health Checks
- [ ] `GET /health` returns `{"status": "healthy"}`
- [ ] `GET /live` returns `{"alive": true}`
- [ ] `GET /startup` returns `{"started": true}`
- [ ] `GET /metrics` returns Prometheus metrics

### 8. Authentication Tests
- [ ] User registration works (`POST /auth/register`)
- [ ] User login works (`POST /auth/login`)
- [ ] Token refresh works (`POST /auth/refresh`)
- [ ] Logout revokes token (`POST /auth/logout`)
- [ ] Protected endpoints require valid token

### 9. API Key Tests
- [ ] API key creation works (`POST /auth/api-keys`)
- [ ] API key listing works (`GET /auth/api-keys`)
- [ ] API key authentication works (use key to access protected endpoint)

### 10. User Management Tests (Admin)
- [ ] Admin can list users (`GET /users/`)
- [ ] Admin can get user details (`GET /users/{id}`)
- [ ] Admin can update user (`PUT /users/{id}`)
- [ ] Admin can delete user (`DELETE /users/{id}`)

### 11. Security Tests
- [ ] Security headers present in responses
- [ ] Rate limiting works (try >10 rapid requests)
- [ ] Invalid tokens rejected (401 Unauthorized)
- [ ] Missing tokens rejected (401 Unauthorized)
- [ ] Non-admin cannot access admin endpoints (403 Forbidden)

### 12. Performance Tests
- [ ] `/health` average latency <50ms
- [ ] `/auth/login` average latency <200ms
- [ ] `/auth/me` throughput >50 req/s
- [ ] Database query latency <10ms

### 13. ML Functionality Tests
- [ ] Sentiment analysis works (if endpoint available)
- [ ] Forecasting works (if endpoint available)
- [ ] News aggregation works (if endpoint available)

## Testing

### 14. Automated Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_auth.py -v
pytest tests/test_users.py -v
pytest tests/test_health.py -v
pytest tests/test_sentiment.py -v
pytest tests/test_forecast.py -v
pytest tests/test_benchmark.py -v
```

### 15. Staging Test Suite
```bash
# Run comprehensive staging tests
python tests/run_staging_tests.py <http://localhost:8000>

# Or with custom URL
python tests/run_staging_tests.py <http://api-staging.example.com:8000>
```

## Monitoring

### 16. Logs
- [ ] API logs being generated
- [ ] Log format is JSON (if `ACAS_MON_LOG_FORMAT=json`)
- [ ] No critical errors in logs
- [ ] PII properly redacted in logs

### 17. Metrics
- [ ] Prometheus metrics available at `/metrics`
- [ ] Grafana dashboard configured (if using Docker)
- [ ] Key metrics being collected:
  - API request rate
  - API latency
  - Error rate
  - Database connection pool

## Sign-Off

### 18. Final Approval
- [ ] All P0/P1 issues fixed
- [ ] All automated tests passing
- [ ] Performance benchmarks met
- [ ] Security review completed
- [ ] Documentation updated
- [ ] Staging environment approved for production deployment

---

**Deployment Approved By**: _______________
**Date**: _______________
**Notes**: _______________

