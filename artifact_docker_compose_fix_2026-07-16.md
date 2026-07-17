# Docker-Compose 集成修复报告 — 2026-07-16

## 问题清单

### P0 致命：docker-compose 不运行 Alembic 迁移

**现象**：`docker-compose up` 使用 `python run.py`（Dockerfile CMD），直接跳过 Alembic。生产环境 `ACAS_ENVIRONMENT=production` 时 `create_tables()` 禁用，app 启动后数据库无任何表。

**根因**：docker-compose.yml 的 `api` 服务未覆盖 `command`，直接使用 Dockerfile 的 `CMD ["python", "run.py"]`。而 K8s deployment.yaml 已用 `command: ["/app/startup.sh"]` 包含 alembic 调用。

**修复**：
1. **docker-compose.yml**：`command: ["/app/startup.sh"]`
2. **startup.sh**：重写为兼容 docker-compose 和 K8s 两种环境：
   - K8s：使用 ConfigMap 注入的独立环境变量（`ACAS_DB_HOST/PORT/USER/PASSWORD/NAME`）
   - docker-compose：解析 `ACAS_DB_URL` 作为 fallback（`postgresql+psycopg://user:pass@host:port/db`）
   - psql 健康检查（等待 PostgreSQL 就绪）+ alembic upgrade head + exec python run.py

### 高危：端口冲突导致容器无法启动

**现象**：
- `db` 服务（`5432:5432`）→ Docker Desktop 内部 PostgreSQL 占用 5432
- `redis` 服务（`6379:6379`）→ 本地 Redis 占用 6379

**修复**：移除 `db` 和 `redis` 的 `ports:` 映射（内部网络 `acas-network` 已足够互通），保留 `api:8000` 端口用于主机访问。

### 中等：ACAS_SECRET_KEY 含 "secret" 被 Pydantic 拒绝

**现象**：`pydantic_core._pydantic_core.ValidationError: ACAS_SECRET_KEY contains insecure pattern 'secret'`

**修复**：使用真正的随机密钥（`secrets.token_urlsafe(32)`）而非测试字符串。

## 修复内容

### 1. startup.sh（新建）

```sh
#!/bin/sh
# 从 ACAS_DB_URL 解析连接信息（如独立变量未设置）
if [ -z "${ACAS_DB_HOST}" ] && [ -n "${ACAS_DB_URL}" ]; then
    ACAS_DB_USER=$(echo "${ACAS_DB_URL}" | sed -E 's|.*://([^:]+):.*|\1|')
    ACAS_DB_PASSWORD=$(echo "${ACAS_DB_URL}" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|')
    ACAS_DB_HOST=$(echo "${ACAS_DB_URL}" | sed -E 's|.*@([^:]+):.*|\1|')
    ACAS_DB_PORT=$(echo "${ACAS_DB_URL}" | sed -E 's|.*:([0-9]+)/.*|\1|')
    ACAS_DB_NAME=$(echo "${ACAS_DB_URL}" | sed -E 's|.*/([^/?]+).*|\1|')
fi
# psql 健康检查 + alembic upgrade head + exec python run.py
```

### 2. docker-compose.yml 变更

```diff
  api:
+   command: ["/app/startup.sh"]
    environment:
      - ACAS_DB_URL=postgresql+psycopg://acas:${DB_PASSWORD:-changeme}@db:5432/acas
+     - ACAS_DB_HOST=db
+     - ACAS_DB_PORT=5432
+     - ACAS_DB_USER=acas
+     - ACAS_DB_PASSWORD=${DB_PASSWORD:-changeme}
+     - ACAS_DB_NAME=acas

  db:
-   ports:
-     - "5432:5432"
    restart: unless-stopped

  redis:
-   ports:
-     - "6379:6379"
```

## 验证结果

### 数据库（7 表创建成功）

```
alembic_version
api_keys
audit_logs
forecast_jobs
news_articles
risk_alerts
users
```

### Alembic 迁移日志

```
[startup] Waiting for PostgreSQL at db:5432...
[startup] PostgreSQL is ready!
[startup] Running Alembic migrations...
INFO  [alembic.runtime.migration] Running upgrade -> baeb152cb3d2, initial schema - create all tables
```

### API 端点

| 端点 | 结果 |
|------|------|
| `GET /health` | ✅ 200 |
| `POST /auth/register` | ✅ 201 created user |
| `GET /users/me` | ✅ 200 |
| `POST /forecast` | ✅ 返回结果 |

### 容器状态

| 容器 | 状态 |
|------|------|
| `acas-v2-db-1` | Healthy |
| `acas-v2-redis-1` | Healthy |
| `acas-v2-api-1` | Healthy |

## 环境差异说明

docker-compose.yml 和 K8s deployment.yaml 的配置现在**完全一致**：

| 维度 | K8s | docker-compose |
|------|-----|----------------|
| 启动命令 | `/app/startup.sh` | `/app/startup.sh` |
| Alembic | ✅ startup.sh | ✅ startup.sh |
| DB 连接 | 独立 env vars (ConfigMap+Secret) | 独立 env vars + URL fallback |
| Redis | 集群 Service | docker network |
| 网络 | K8s CNI | bridge |

## 注意事项

1. **本地 PostgreSQL**：docker-compose 的 `postgres_data` 卷可能与本地 PG 数据目录冲突。测试时需临时停止本地 PostgreSQL 服务。
2. **密钥**：生产部署必须使用真正随机的 `ACAS_SECRET_KEY`（不含 "secret" 关键词）。
3. **端口**：移除 db/redis 的主机端口映射，api 的 8000 端口保留用于主机访问。
