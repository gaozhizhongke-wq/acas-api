# ACAS v2 运行手册

## 1. 日常维护

### 1.1 健康检查

```bash
# 检查应用是否健康
curl http://localhost:8000/health

# 检查应用是否就绪 (所有依赖正常)
curl http://localhost:8000/ready

# 检查日志
tail -f logs/acas.log
```

### 1.2 监控指标

访问Grafana仪表板:
```
http://localhost:3000/d/acas/acas-v2-performance
```

关键指标:
- Request Rate (请求率)
- Error Rate (错误率)
- Latency P95 (延迟P95)
- Active Requests (活跃请求数)
- Database Connections (数据库连接数)
- Redis Memory Usage (Redis内存使用)

### 1.3 日志查看

```bash
# 应用日志
tail -f logs/acas.log

# 错误日志
grep ERROR logs/acas.log

# 审计日志 (数据库)
psql -h localhost -U acas -d acas -c "SELECT * FROM audit_logs ORDER BY created_at DESC LIMIT 10;"
```

---

## 2. 故障排查

### 2.1 应用无法启动

**症状**: `uvicorn` 启动失败

**排查步骤**:
```bash
# 1. 检查Python版本
python --version  # 需要 3.11+

# 2. 检查依赖
pip install -r requirements.txt

# 3. 检查配置文件
cat .env

# 4. 检查端口占用
netstat -an | grep 8000  # Linux/Mac
netstat -an | findstr 8000  # Windows

# 5. 查看启动日志
python run.py 2>&1 | tee startup.log
```

**常见原因**:
- ❌ Python版本不匹配 → 使用pyenv/conda管理版本
- ❌ 依赖缺失 → `pip install -r requirements.txt`
- ❌ 配置文件错误 → 检查 `.env` 文件格式
- ❌ 端口被占用 → 更改 `ACAS_API_PORT` 或停止占用进程

---

### 2.2 数据库连接失败

**症状**: `/ready` 返回503, 日志显示 `database connection failed`

**排查步骤**:
```bash
# 1. 检查PostgreSQL是否运行
pg_isready -h localhost -p 5432

# 2. 测试数据库连接
psql -h localhost -U acas -d acas -c "SELECT 1;"

# 3. 检查数据库配置
cat .env | grep DB_URL

# 4. 检查数据库日志
sudo tail -f /var/log/postgresql/postgresql-17-main.log  # Linux
# Windows: 查看 Event Viewer
```

**常见原因**:
- ❌ PostgreSQL未启动 → `systemctl start postgresql` (Linux) 或 `net start postgresql-x64-17` (Windows)
- ❌ 密码错误 → 检查 `.env` 中的 `ACAS_DB_URL`
- ❌ 数据库不存在 → `createdb -U acas acas`
- ❌ 权限不足 → `GRANT ALL PRIVILEGES ON DATABASE acas TO acas;`

---

### 2.3 Redis连接失败

**症状**: `/ready` 返回503, 日志显示 `redis connection failed`

**排查步骤**:
```bash
# 1. 检查Redis是否运行
redis-cli ping  # 应返回 PONG

# 2. 检查Redis配置
cat .env | grep REDIS_URL

# 3. 检查Redis日志
tail -f /var/log/redis/redis-server.log  # Linux
# Windows: 查看 Redis 服务日志
```

**常见原因**:
- ❌ Redis未启动 → `systemctl start redis` (Linux) 或 `net start Redis` (Windows)
- ❌ 密码错误 → 检查 `.env` 中的 `ACAS_REDIS_URL`
- ❌ 内存不足 → `redis-cli info memory` 检查内存使用

---

### 2.4 API请求返回500错误

**症状**: API请求返回HTTP 500

**排查步骤**:
```bash
# 1. 查看应用日志
grep ERROR logs/acas.log | tail -20

# 2. 查看详细错误堆栈
LOG_LEVEL=DEBUG python run.py

# 3. 检查数据库连接
curl http://localhost:8000/ready

# 4. 检查Redis连接
redis-cli ping
```

**常见原因**:
- ❌ 数据库查询错误 → 检查SQL语法, 表结构
- ❌ Redis操作错误 → 检查Redis数据类型
- ❌ ML模型加载失败 → 检查模型文件是否存在
- ❌ 外部API调用失败 → 检查网络连接, API密钥

---

### 2.5 性能问题

**症状**: API响应慢, 延迟高

**排查步骤**:
```bash
# 1. 查看Prometheus指标
curl http://localhost:9090/metrics

# 2. 查看慢查询日志
psql -h localhost -U acas -d acas -c "SELECT query, mean_time, calls FROM pg_stat_statements ORDER BY mean_time DESC LIMIT 10;"

# 3. 查看Redis慢查询
redis-cli slowlog get 10

# 4. 查看系统资源
top  # Linux/Mac
tasklist  # Windows
```

**常见原因**:
- ❌ 数据库缺少索引 → 运行 `scripts/optimize_performance.py`
- ❌ 数据库查询未优化 → 使用 `EXPLAIN ANALYZE` 分析查询计划
- ❌ Redis缓存未命中 → 检查缓存键, TTL
- ❌ ML模型推理慢 → 使用GPU加速, 或简化模型

---

## 3. 灾难恢复

### 3.1 数据库故障

**场景**: 数据库服务器崩溃

**恢复步骤**:
```bash
# 1. 停止应用
sudo systemctl stop acas  # Linux
# Windows: Ctrl+C 或停止服务

# 2. 从备份恢复
./scripts/disaster_recovery.sh

# 3. 验证数据完整性
psql -h localhost -U acas -d acas_restore -c "SELECT COUNT(*) FROM users;"

# 4. 更新应用配置使用恢复的数据库
sed -i 's/ACAS_DB_URL=.*/ACAS_DB_URL=postgresql+psycopg:\/\/acas:password@localhost:5432\/acas_restore/' .env

# 5. 重启应用
sudo systemctl start acas  # Linux
# Windows: python run.py
```

---

### 3.2 应用服务器故障

**场景**: 应用服务器硬件故障

**恢复步骤**:
```bash
# 1. 在新服务器上部署应用
git clone <repo>
cd acas-v2
pip install -r requirements.txt

# 2. 复制配置文件
scp user@old-server:/path/to/.env .env

# 3. 连接到现有数据库和Redis
# (确保 .env 中的数据库和Redis配置正确)

# 4. 启动应用
python run.py

# 5. 更新负载均衡器配置 (如果使用)
# (指向新服务器)
```

---

### 3.3 数据损坏

**场景**: 数据文件损坏

**恢复步骤**:
```bash
# 1. 停止应用
sudo systemctl stop acas

# 2. 从最新备份恢复
LATEST_BACKUP=$(ls -t backups/*.sql | head -1)
psql -h localhost -U acas -d acas < $LATEST_BACKUP

# 3. 验证数据
psql -h localhost -U acas -d acas -c "SELECT COUNT(*) FROM users;"

# 4. 重启应用
sudo systemctl start acas
```

---

## 4. 性能优化

### 4.1 数据库优化

```bash
# 1. 创建索引
python scripts/optimize_performance.py

# 2. 更新统计信息
psql -h localhost -U acas -d acas -c "ANALYZE;"

# 3. 优化PostgreSQL配置
# 编辑 postgresql.conf, 参考 scripts/optimize_performance.py 中的推荐配置
```

### 4.2 Redis优化

```bash
# 1. 检查内存使用
redis-cli info memory

# 2. 优化Redis配置
# 编辑 redis.conf, 参考 scripts/optimize_performance.py 中的推荐配置

# 3. 清理过期键
redis-cli --scan --pattern "*" | xargs redis-cli del
```

### 4.3 应用优化

```bash
# 1. 启用缓存
# 在 .env 中设置 ACAS_CACHE_ENABLED=true

# 2. 调整worker数量
# 在 .env 中设置 ACAS_API_WORKERS=8 (根据CPU核心数调整)

# 3. 启用异步任务
# 配置Celery/RQ处理后台任务
```

---

## 5. 安全维护

### 5.1 更新依赖

```bash
# 1. 检查过期依赖
pip list --outdated

# 2. 更新依赖
pip install -U -r requirements.txt

# 3. 检查安全漏洞
pip install safety
safety check
```

### 5.2 轮换密钥

```bash
# 1. 生成新的JWT密钥
python -c "import secrets; print(secrets.token_urlsafe(32))"

# 2. 更新 .env 中的 ACAS_SECRET_KEY

# 3. 重启应用 (所有用户需重新登录)

# 4. 轮换API密钥 (数据库)
psql -h localhost -U acas -d acas -c "UPDATE api_keys SET key_hash = ...;"
```

### 5.3 审计日志审查

```bash
# 1. 查看最近的审计日志
psql -h localhost -U acas -d acas -c "
  SELECT action, user_id, ip_address, created_at
  FROM audit_logs
  ORDER BY created_at DESC
  LIMIT 100;
"

# 2. 查找异常行为
psql -h localhost -U acas -d acas -c "
  SELECT user_id, COUNT(*) as login_count
  FROM audit_logs
  WHERE action = 'login'
  AND created_at > NOW() - INTERVAL '1 hour'
  GROUP BY user_id
  HAVING COUNT(*) > 10;
"
```

---

## 6. 备份与恢复

### 6.1 自动备份

```bash
# 1. 配置cron job (Linux) 或 Task Scheduler (Windows)
# 每天凌晨2点备份

# Linux:
# crontab -e
# 0 2 * * * /path/to/scripts/backup.sh

# Windows:
# 创建计划任务, 每天2:00运行 backup.ps1
```

### 6.2 手动备份

```bash
# 1. 备份数据库
pg_dump -h localhost -U acas acas > backups/manual_$(date +%Y%m%d_%H%M%S).sql

# 2. 备份配置文件
tar -czf backups/config_$(date +%Y%m%d_%H%M%S).tar.gz .env config.py

# 3. 备份日志
tar -czf backups/logs_$(date +%Y%m%d_%H%M%S).tar.gz logs/
```

### 6.3 恢复

```bash
# 1. 恢复数据库
psql -h localhost -U acas -d acas < backups/manual_20260702_010000.sql

# 2. 恢复配置文件
tar -xzf backups/config_20260702_010000.tar.gz

# 3. 重启应用
sudo systemctl restart acas
```

---

## 7. 联系支持

**技术支持**:
- Email: support@acas.com
- 紧急联系电话: +86 400-XXX-XXXX

**安全事件报告**:
- Email: security@acas.com
- PGP Key: https://acas.com/pgp-key.asc

**文档**:
- API文档: https://docs.acas.com/api
- 运行手册: https://docs.acas.com/operations

---

**最后更新**: 2026-07-02
**版本**: 2.0.0
