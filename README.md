# ACAS v2 - Africa Commodity Analytics System

企业级大宗商品分析系统，集成 TimesFM 销售预测与 WorldMonitor 舆情监控。

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                        ACAS v2                               │
├─────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                         │
│  ├── /auth      - JWT 认证与 API Key 管理                    │
│  ├── /forecast  - TimesFM 销售预测                           │
│  └── /intel     - WorldMonitor 舆情监控                      │
├─────────────────────────────────────────────────────────────┤
│  Core Services                                               │
│  ├── Security   - Argon2 + JWT + Fernet 加密                 │
│  ├── Database   - PostgreSQL + SQLAlchemy 2.0                │
│  ├── Cache      - Redis 连接池 + 滑动窗口限流                │
│  └── Logging    - 结构化 JSON 日志 + PII 脱敏                │
├─────────────────────────────────────────────────────────────┤
│  ML & Intelligence                                           │
│  ├── TimesFM Engine    - Google 时序预测 (200M 参数)         │
│  ├── Sales Predictor   - 业务层预测 + 库存优化               │
│  ├── News Aggregator   - 多源 RSS 聚合 + 去重              │
│  ├── Sentiment Analyzer - Transformer 情感分析               │
│  └── Intelligence Engine - 风险预警 + 多维度评分             │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 本地开发

```bash
# 1. 克隆并进入目录
cd acas-v2

# 2. 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入数据库连接等信息

# 5. 启动服务
uvicorn src.api.main:app --reload
```

### Docker 部署

```bash
# 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f api

# 执行数据库迁移
docker-compose exec api alembic upgrade head
```

## API 端点

### 认证
```bash
POST /auth/register    # 注册
POST /auth/login       # 登录获取 JWT
POST /auth/refresh     # 刷新 Token
```

### 销售预测 (TimesFM)
```bash
POST /forecast/sales
{
  "category": "electronics",
  "region": "africa",
  "historical_data": [...],
  "forecast_days": 30
}

POST /forecast/inventory
{
  "product_id": "SKU-123",
  "current_stock": 1000,
  "lead_time_days": 14,
  "historical_sales": [...]
}
```

### 舆情监控 (WorldMonitor)
```bash
GET /intelligence/market              # 市场情报总览
GET /intelligence/alerts?min_level=HIGH  # 风险预警
POST /intelligence/monitor/start      # 启动实时监控
```

## 配置说明

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `ACAS_SECRET_KEY` | JWT 签名密钥 | 必须设置 |
| `ACAS_DB_URL` | PostgreSQL 连接 | localhost |
| `ACAS_REDIS_URL` | Redis 连接 | localhost |
| `ACAS_RL_ENABLED` | 启用限流 | true |
| `ACAS_ML_TIMESFM_ENABLED` | 启用 TimesFM | true |

## 生产检查清单

- [ ] 修改 `ACAS_SECRET_KEY`（至少 32 字符）
- [ ] 配置 `ACAS_ENCRYPTION_KEY`（Fernet 密钥）
- [ ] 使用 PostgreSQL 而非 SQLite
- [ ] 启用 Redis 缓存
- [ ] 配置 Sentry DSN 错误监控
- [ ] 设置 HTTPS/TLS
- [ ] 配置防火墙规则
- [ ] 启用审计日志

## 技术栈

- **Backend**: FastAPI, SQLAlchemy 2.0, Pydantic v2
- **Database**: PostgreSQL 16, Redis 7
- **ML**: TimesFM, Transformers, PyTorch
- **Security**: Argon2, JWT, Fernet
- **Ops**: Docker, Prometheus, structured logging

## License

MIT
