# ACAS v2 Demo → 生产级 交付计划

**目标**: 将当前 Demo 状态提升至可生产部署标准
**时间**: 2026-06-24
**基准**: 当前评分 ~97/100（代码维度），实际生产就绪度 ~15%

---

## 阶段一：基础设施生产化（✅ 已完成）

### 1.1 数据库：彻底脱离 SQLite
- [x] 确保 PostgreSQL 连接正常（asyncpg→psycopg 已迁移完成）
- [x] Docker Compose 中 PostgreSQL 健康检查完善
- [x] Alembic 迁移脚本验证通过
- [x] 连接池参数优化（pool_size, max_overflow 已配置）
- [ ] 数据库加密连接（SSL）配置支持 — 待添加

### 1.2 Redis 生产化
- [x] 确保限流功能在 Redis 可用时正常工作
- [x] Token 黑名单在 Redis 中持久化
- [x] Redis 连接池和重连逻辑完善
- [x] Redis ACL 密码认证配置

### 1.3 Docker 生产配置
- [x] Dockerfile 多阶段构建（builder + production 两阶段）
- [x] docker-compose.yml 安全加固（non-root user, security_opt）
- [x] 环境变量验证启动检查（ACAS_SECRET_KEY 必须设置）
- [x] 健康检查完善（/health 包含所有依赖状态）
- [x] 日志输出到 stdout + Loki/Promtail 收集

---

## 阶段二：安全加固（✅ 大部分已完成）

### 2.1 认证安全
- [x] production 模式启动时强制校验 ACAS_SECRET_KEY 不是默认值
- [x] Refresh Token 持久化到数据库
- [x] API Key 创建审计日志 ✅（已集成）
- [ ] 登录失败次数限制（暴力破解防护）— 待添加
- [ ] Token 请求绑定（防止 token 重放）— 可选

### 2.2 数据安全
- [x] 敏感配置通过环境变量/Docker secrets 注入
- [ ] API 响应中敏感字段脱敏 — 待添加
- [x] CORS 白名单严格控制（production 默认空）
- [x] Rate limit production 配置完善

### 2.3 审计日志
- [x] 审计日志持久化到数据库（AuditLog 模型已写入）
- [x] 关键操作记录：登录/注销、API Key 创建/撤销、用户创建、密码修改 ✅

---

## 阶段三：测试覆盖（✅ 已完成）

### 3.1 单元测试
- [x] conftest.py 已修复（SQLite 文件模式 + 双模块 patch）
- [x] 运行 pytest — 79 passed, 1 skipped
- [x] JSONB 与测试兼容性已验证

### 3.2 集成测试
- [x] 完整认证流程测试（注册→登录→refresh→logout）
- [x] API Key 生命周期测试
- [x] 限流功能测试
- [x] 错误处理测试（各种 4xx/5xx）

### 3.3 覆盖率
- [ ] pytest --cov=src 目标：≥80% — 待完成

---

## 阶段四：可观测性（✅ 已完成）

### 4.1 结构化日志
- [x] structlog 已配置
- [x] 日志级别路由已配置
- [x] 请求关联 ID 全链路传递
- [ ] PII 脱敏（邮箱、密码不在日志中出现）— 待添加

### 4.2 Prometheus 指标
- [x] /metrics 基础指标已实现
- [x] Prometheus + Grafana 已配置
- [x] Loki + Promtail 日志聚合已配置
- [ ] 扩展指标（请求延迟直方图等）— 后续迭代

### 4.3 告警
- [x] Docker Compose monitoring profile 验证
- [x] 关键告警规则已创建（错误率 >5%, P99 >2s, DB/Redis 离线）
- [x] Grafana 自动配置数据源 + 概览仪表盘

---

## 阶段五：ML 引擎真实化（第5优先级 — 视部署环境）

### 5.1 情感分析
- [ ] transformers + torch 安装验证
- [ ] XLM-RoBERTa 模型下载和加载
- [ ] 推理延迟测试（目标：<500ms/条）
- [ ] 如果 GPU 不可用：使用 ONNX Runtime 量化版

### 5.2 预测引擎
- [ ] ARIMA 已可用 ✅
- [ ] Prophet 安装验证（pystan 依赖）
- [ ] LSTM 需要足够数据量 — 可延后

### 5.3 新闻抓取
- [ ] RSS 源可达性验证（当前超时是网络问题，非代码 bug）
- [ ] GDELT API 可达性验证
- [ ] 抓取失败重试机制
- [ ] 超时设置合理化

---

## 阶段六：部署自动化（✅ 已完成）

### 6.1 CI/CD
- [x] GitHub Actions CI workflow 已验证
- [x] Docker 镜像构建 + GHCR 推送
- [x] 自动测试在 CI 中运行
- [x] Deploy workflow（SSH → docker-compose）

### 6.2 部署文档
- [x] Makefile 提供快捷命令
- [x] 环境变量清单（.env.example + docker-compose.yml）
- [x] Docker 部署已验证
- [ ] 故障排查指南 — 待编写
- [ ] 回滚流程 — 待编写

---

## 执行策略

**累计进度**：
- 阶段一：95% ✅
- 阶段二：90% ✅
- 阶段三：85% ✅
- 阶段四：90% ✅
- 阶段五：0%（依赖部署环境）
- 阶段六：85% ✅

**剩余待办**：
- SSL 数据库连接
- 暴力破解防护
- API 响应敏感字段脱敏
- PII 日志脱敏
- 扩展 Prometheus 指标
- 测试覆盖率达 ≥80%
- 故障排查指南 + 回滚流程
