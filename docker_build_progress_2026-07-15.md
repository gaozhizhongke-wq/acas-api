# ACAS v2 — Docker 镜像构建进度（2026-07-15）

## 当前状态
- **目标**：构建可运行的 ACAS v2 生产 Docker 镜像（`acas:v2.0.0` / `acas:latest`）。
- **构建会话**：后台运行中（session `fast-wharf`，pid 27172），命令 `docker build -t acas:v2.0.0 -t acas:latest .`
- **日志**：`build.log`
- **预计剩余**：~30 分钟（外部网络瓶颈，pip ~35KB/s，apt 镜像 ~18KB/s）。

## 关键发现与根因（重要）
1. **原 `acas:smoke` 镜像无法启动 App**：`api.main` 在模块顶层需要 `numpy`/`pandas`（来自 `ml/timesfm_engine.py`），以及 `aiohttp`/`feedparser`（来自 `sentiment/news_aggregator.py`）。smoke 镜像只装了核心依赖，缺这些，导致 `import api.main` 直接崩溃。→ smoke 镜像被判定为不完整、不可用，已弃用。
2. **ML 重型依赖是惰性导入（设计正确）**：`torch`/`transformers`/`prophet`/`statsmodels` 在 `timesfm_engine.py` 与 `sentiment_analyzer.py` 中均为**函数内惰性导入**，且 `requirements.txt` 已将它们注释掉（torch/transformers/prophet）。因此：
   - 构建**无需**下载 ~1GB 的 torch/transformers。
   - 镜像内 App 可正常启动，所有核心端点可用；ML 端点（forecast/sentiment/intelligence）在模型不可用时优雅降级（返回错误而非崩溃）。
   - 这与项目"ML 条件初始化 + 优雅降级"设计一致。

## 已修复 / 已做
- **重写 `Dockerfile`**（修复原语法错误 + 去掉无用 gcc 编译链）：
  - builder 阶段：`python:3.11-slim` + venv + `pip install -r requirements.txt`（全部为 manylinux 预编译 wheel，无源码编译）。
  - runtime 阶段：仅装 `libpq5` + `curl`（psycopg[binary] 自带 libpq，无需 gcc），非 root 用户 `acas`，HEALTHCHECK 用 curl 探 `/health`。
  - 复制 `run.py`/`src/`/`alembic/`/`alembic.ini`/`.env.example`/`deploy/`。
- **新增 `.dockerignore`**：排除 `.env`/`.git`/`tests`/`docs`/`htmlcov`/临时脚本/`*.ps1`/`*.sh` 等，避免密钥与无关文件进入构建上下文。
- **生成验证密钥**：`.verify_secret.txt`（ACAS_SECRET_KEY，用于验证）。
- **编写验证脚本** `verify_docker.ps1`：构建完成后用 sqlite + 关闭 Redis 限流 + ML 禁用启动容器，验证 `/health`、`/ready`、`/auth/register`、`/auth/login`、`/users/me` 全链路。

## 验证计划（构建完成后执行）
```powershell
# 1) 快速功能验证（sqlite，无需 PG/Redis）
powershell -ExecutionPolicy Bypass -File verify_docker.ps1

# 2) 生产式全栈验证（postgres + redis，按 docker-compose.yml）
$env:ACAS_SECRET_KEY = (Get-Content .verify_secret.txt -Raw).Trim()
$env:DB_PASSWORD = 'acas_prod_pw_change_me'
docker compose up -d
# 检查：docker compose ps；curl http://localhost:8000/health
```

## 待确认 / 风险
- **构建网络慢**：apt 镜像 deb.debian.org 实测 ~18KB/s，pip ~35KB/s。若后续需重建，可在 Dockerfile 中改用国内 pip 镜像（`-i https://pypi.tuna.tsinghua.edu.cn/simple`）并去掉 curl（改用 Python 健康探针）以提速。
- **ML 端点**：镜像不含 torch/transformers/prophet，forecast/sentiment/intelligence 的 ML 路径会降级。若生产需要 ML，需单独构建含 torch/transformers 的镜像（另写 Dockerfile.ml）。
- **Alembic 迁移**：当前 `run.py` 在非 production 下自动 `create_tables()`；生产环境应改用 Alembic（此前的已知阻塞项，psycopg 已替换 asyncpg）。compose 生产验证时不自动建表，需先 `alembic upgrade head`（待办）。
