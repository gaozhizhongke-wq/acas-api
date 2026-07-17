# ACAS v2 工业级评估报告 — 2026-07-16

**评估方法：逐项核查，有疑义的标注"未验证"，禁止美化**

---

## 总评：NOT 工业级 — 属于"包装精美的 Demo/POC"

**综合完成度：~55%**，距离工业级（≥90%）差距巨大。

---

## 一、功能完整性 — 50/100 ❌

### 1.1 核心 API 功能

| 端点 | 状态 | 说明 |
|------|------|------|
| `/auth/register` | ✅ 实测通过 | |
| `/auth/login` | ✅ 实测通过 | 含暴力破解防护 |
| `/auth/refresh` | ✅ 代码存在 | 未独立端到端验证 |
| `/users/me` | ✅ 实测通过 | JWT Bearer Token |
| `/users/{id}` | ✅ 代码存在 | 未独立端到端验证 |
| `/forecast` | ⚠️ 部分通过 | **仅 ARIMA 可用**，Prophet/LSTM 均为 no-op |
| `/intelligence/news` | ⚠️ 部分通过 | **规则引擎**，ML 层已禁用 |
| `/sentiment` | ⚠️ 部分通过 | **规则引擎**，无 XLM-RoBERTa |
| `/health` | ✅ 实测通过 | |
| `/metrics` | ✅ 代码存在 | 未端到端验证 |
| `/ready` | ✅ 503 预期 | Redis 不可用时正确降级 |

### 1.2 ML 功能真实性 — **致命欺骗**

```
Docker 镜像内已安装包：
✅ fastapi, uvicorn, psycopg, redis, sentry-sdk, structlog
❌ torch (0 bytes)
❌ transformers (0 bytes)
❌ prophet (0 bytes)
❌ accelerate (0 bytes)
❌ timesfm (0 bytes)
```

**实际情况**：
- `timesfm_engine.py`：Prophet → "install prophet" + LSTM → "install torch" + TimesFM → "no GPU" → 最终仅 ARIMA（纯 statsmodels）+ Holt-Winters（规则逻辑，非真正预测模型）
- `sentiment_analyzer.py`：`No module named 'transformers'` → 纯规则（关键词匹配）
- `intelligence_engine.py`：基于 `sentiment_analyzer`（规则引擎）

**结论**：这是一个**规则引擎系统**，不是 ML 预测平台。所有"AI 预测"均为假象。

### 1.3 数据库 Schema

✅ 6 表全部创建（users, api_keys, audit_logs, forecast_jobs, news_articles, risk_alerts）

❌ 缺失关键功能：
- `refresh_tokens` 表未在迁移中存在（Memory 笔记提到过）
- 无数据保留/过期策略
- 无 full-text search 索引
- news_articles 无 source 字段区分

---

## 二、测试覆盖 — 64/100 ⚠️

```
Total                             1513    544    64%

src\core\rate_limit.py            144     87     40%  ← 暴力破解防护，关键模块
src\api\routes\health.py          41      27     34%  ← 健康检查，关键模块
src\api\routes\auth.py            194     88     55%  ← 认证，关键模块
src\api\routes\users.py          117     55     53%  ← 用户管理，关键模块
src\api\routes\intelligence.py    37     17     54%  ← 业务逻辑
src\api\main.py                   170     71     58%  ← 启动/生命周期

src\core\security.py              165     37     78%  ✅
src\core\config.py                124      8     94%  ✅
src\api\models.py                108      2     98%  ✅
```

**问题**：
1. CI 中 `ACAS_RATE_LIMIT_ENABLED: "false"` — 暴力破解防护代码路径在 CI 中被完全禁用，永远测不到
2. 关键安全模块 `rate_limit.py` 仅 40% 覆盖率
3. `health.py` 仅 34% — 4 种 probe（startup/live/ready/health）仅覆盖部分
4. `auth.py` 仅 55% — refresh token rotation, logout-all 等路径未充分测试

---

## 三、CI/CD 管道 — 35/100 ❌

### 3.1 Git 仓库无 Remote — **P0 阻断**

```
git remote -v
→ (无输出)
```

**影响**：无法推送到 GitHub → 无法触发 CI/CD → 无法构建 Docker 镜像 → 整个自动化流水线完全失效。

### 3.2 GitHub Actions 配置问题

| 问题 | 严重性 | 说明 |
|------|--------|------|
| `bandit ... \|\| true` | 高 | 安全扫描失败被忽略，高危漏洞不阻断 |
| `ACAS_RATE_LIMIT_ENABLED: "false"` | 高 | 禁用率限→测试路径覆盖不全 |
| 无 Redis password in deploy.yml | 中 | 依赖 docker-compose 默认值 |
| `needs: test` 依赖 | 中 | test 超时（ML 模块挂起）则 build 不跑 |

### 3.3 Alembic 迁移覆盖 ✅

- 迁移脚本存在：`baeb152cb3d2_initial_schema_create_all_tables.py`
- docker-compose 实测通过：`alembic upgrade head` 成功
- startup.sh 正确集成

---

## 四、部署配置 — 60/100 ⚠️

### 4.1 Docker

✅ 多阶段构建（~1.06GB）
✅ 非 root 用户（acas:1000）
✅ startup.sh 入口（alembic + python run.py）
✅ 健康检查（liveness/readiness/startup probes）
❌ 无 healthcheck in startup.sh — 仅依赖 Python 启动成功

### 4.2 Kubernetes

| 文件 | 状态 | 说明 |
|------|------|------|
| deployment.yaml | ⚠️ 部分 | readinessProbe 已改 `/health` ✅；image tag 占位符 |
| secret.yaml | ⚠️ 部分 | 本地真实密钥已填充 ✅；但 Git 未推送 |
| ingress.yaml | ✅ | TLS + 安全头 + 速率限制 |
| configmap.yaml | ✅ | SSL_MODE=disable ✅ |
| startup.sh | ✅ | K8s 专用版本已创建 |

**致命问题**：`ghcr.io/acas-project/acas:v2.0.0` 为虚构镜像，无真实 GitHub 仓库则无法推送。

### 4.3 docker-compose

✅ startup.sh 集成 ✅
✅ 移除端口冲突 ✅
✅ 环境变量完整传递 ✅

---

## 五、安全性 — 70/100 ⚠️

### 已达标

| 机制 | 状态 |
|------|------|
| JWT Bearer Token | ✅ 实测有效 |
| Refresh Token Rotation | ✅ 代码存在 |
| Token Blacklist | ✅ 代码存在 |
| API Key Hash | ✅ bcrypt |
| 暴力破解防护 | ✅ `is_login_blocked/record_login_failure/clear_login_attempts` |
| PII 脱敏 | ✅ email/name/ip |
| 审计日志 | ✅ 9 端点已集成 |
| SQL 注入防护 | ✅ SQLAlchemy ORM |
| 密钥模式验证 | ✅ `changeme/secret/password` 拒绝 |
| CORS 安全头 | ✅ |
| rate limit 全局 | ✅ Redis |
| SSL/TLS | ✅ config 支持 |

### 未达标

| 机制 | 状态 |
|------|------|
| Rate Limit 暴力破解 | ❌ **CI 中被禁用**（见 3.2） |
| 渗透测试 | ❌ 未执行 |
| 依赖漏洞扫描 | ❌ `bandit ... \|\| true` |
| API 配额/计费 | ❌ 无 |
| 多租户数据隔离 | ❌ 未验证 |
| TLS 终止 | ⚠️ 仅 ingress 层 |
| 密钥轮换 | ❌ 无自动化 |

---

## 六、可观测性 — 65/100 ⚠️

| 组件 | 状态 | 说明 |
|------|------|------|
| 结构化日志 | ✅ JSON + correlation_id | |
| Prometheus metrics | ✅ `/metrics` 端点 | 仅基本指标，未验证导出 |
| Sentry | ✅ 集成，已配置 DSN | |
| Loki + Promtail | ⚠️ docker-compose 中 | staging/prod 需配置 |
| Grafana | ⚠️ docker-compose 中 | staging/prod 需配置 |
| 健康检查端点 | ✅ 4 种 probe | |
| 日志等级控制 | ✅ env var | |

**未达标**：
- 链路追踪（distributed tracing）完全缺失
- 告警规则未配置（无 PagerDuty/Slack/邮件告警规则）
- 监控仪表盘未配置（Grafana 面板需手动创建）
- 日志保留策略未定义

---

## 七、可靠性 — 55/100 ❌

| 机制 | 状态 |
|------|------|
| 高可用（多副本） | ✅ K8s HPA 2-20 副本 |
| Pod Anti-Affinity | ✅ |
| 优雅终止（60s） | ✅ |
| 资源限制 | ✅ CPU/内存 |
| Init Containers | ✅ PostgreSQL/Redis 等待 |
| Circuit Breaker | ⚠️ 代码存在，未验证 |
| 灾难恢复 | ❌ 无备份/恢复流程 |
| 故障切换 | ❌ 无多区域部署 |
| 数据备份 | ❌ 无 |

---

## 八、文档 — 60/100 ⚠️

✅ `docs/production_deployment.md`
✅ `docs/rollback_guide.md`
❌ 架构图缺失
❌ API 文档缺失（无 OpenAPI spec 托管说明）
❌ 运维手册缺失（无 on-call runbook）
❌ 灾难恢复手册缺失
❌ 安全加固指南缺失

---

## 九、测试质量 — 55/100 ❌

- **493 个测试文件**，但：
  - 存在大量冗余测试（`test_final_2pp.py`, `test_final_correct.py`, `test_coverage_push_80.py` 等相似文件）
  - 部分测试仅覆盖推送覆盖率，无实际断言
  - 全量测试在 Windows 上因 ML 模块挂起而超时
  - CI 中率限功能被禁用 → 测试路径与生产不符

---

## 十、运营就绪度 — 40/100 ❌

| 维度 | 状态 |
|------|------|
| 环境配置管理 | ⚠️ .env.example 存在，.env 未入 Git |
| 密钥轮换 | ❌ 无 |
| 监控告警 | ❌ 无告警规则 |
| 日志聚合 | ⚠️ Loki 已配置，未验证 |
| 灾难恢复 | ❌ 无备份 |
| SLO/SLA 定义 | ❌ 无 |
| 灰度发布 | ❌ 无 |
| 回滚自动化 | ⚠️ 手动流程 |
| 数据库迁移策略 | ⚠️ Alembic 存在，未验证回滚 |

---

## 致命问题汇总（P0/P1/P2）

### P0 — 阻塞工业级交付

| # | 问题 | 影响 |
|---|------|------|
| P0-1 | **Git 无 remote** | CI/CD 完全失效，无法构建/部署 |
| P0-2 | **ML 功能为假** | 核心卖点不存在，系统本质是规则引擎 |
| P0-3 | **测试覆盖率 64%** | 低于 80% 基线，大量关键路径未覆盖 |
| P0-4 | **CI 中率限被禁用** | `ACAS_RATE_LIMIT_ENABLED=false` → 暴力破解防护路径未测试 |

### P1 — 严重影响可靠性

| # | 问题 | 影响 |
|---|------|------|
| P1-1 | `bandit ... \|\| true` | 安全扫描形同虚设 |
| P1-2 | K8s image tag 占位符 | 无法实际部署到集群 |
| P1-3 | 无灾难恢复流程 | 数据丢失风险 |
| P1-4 | 无监控告警规则 | 故障无感知 |

### P2 — 显著差距

| # | 问题 |
|---|------|
| P2-1 | 监控/Grafana 面板需手动创建 |
| P2-2 | 无 API 文档托管 |
| P2-3 | 大量冗余测试文件需清理 |
| P2-4 | 无渗透测试 |
| P2-5 | 无灰度发布/CD |

---

## 对比：Demo/POC vs 工业级

| 维度 | Demo/POC ✅ | 工业级 ❌ |
|------|------------|---------|
| 功能演示 | ✅ | ❌ ML 功能不存在 |
| 本地运行 | ✅ | ✅ |
| 代码量 | ✅ | ❌ 无 remote，CI 不通 |
| 配置完整性 | ✅ | ❌ 测试覆盖率 64% |
| 部署配置 | ✅ | ❌ image 占位符 |
| 安全性 | ⚠️ | ❌ CI 禁用安全路径 |

**结论**：这是一套**架构完整但核心功能造假、CI/CD 完全失效的演示系统**。接近工业级外壳，但内核是 Demo。

---

## 修复优先级

1. **立即修复**（1-2 天）：
   - 配置 GitHub remote + 推送
   - 完善 CI（移除 `|| true`，启用率限测试）
   - 提升覆盖率至 80%+
   - 决定 ML 策略（真正实现或移除虚假声明）

2. **短期修复**（1 周）：
   - 配置 Grafana 面板 + 告警规则
   - 灾难恢复文档 + 备份策略
   - 渗透测试

3. **中期完善**（1 个月）：
   - API 文档（OpenAPI）
   - 多区域部署
   - 灰度发布
   - 密钥自动轮换
