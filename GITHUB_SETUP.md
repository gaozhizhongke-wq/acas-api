# GitHub 仓库与 CI/CD 配置指南

## 当前状态

| 项目 | 状态 | 说明 |
|------|------|------|
| 代码提交 | ✅ 已完成 | `git log` 显示 5+ 次生产提交 |
| 测试覆盖率 | ✅ 80.56% | 399 passed, 4 skipped, 0 failed |
| Docker 镜像 | ✅ 已构建 | `acas:latest` / `acas:v2.0.0` (1.15GB) |
| 容器 ML 验证 | ✅ 已通过 | 注册→登录→sentiment 全流程正常，ML 优雅降级 |
| K8s 镜像 tag | ✅ 已修复 | `deployment.yaml` 支持本地镜像 + GHCR |
| Git remote | ❌ 待配置 | **阻塞项：需用户创建 GitHub 仓库** |
| CI/CD 触发 | ❌ 待触发 | 依赖 Git remote + 首次 push |

## 步骤 1：创建 GitHub 仓库

在 https://github.com/new 创建仓库：

- **Repository name**: `acas-api`
- **Visibility**: Private（推荐，含密钥配置）
- **Initialize**: 不要勾选 README/.gitignore/LICENSE（本地已有）

## 步骤 2：添加远程并推送

```powershell
cd C:\Users\HUAWEI\.qclaw\workspace-agent-eb98a2a2\acas-v2

# 添加远程（将 <YOUR_GITHUB_USER> 替换为你的用户名）
git remote add origin https://github.com/<YOUR_GITHUB_USER>/acas-api.git

# 推送 main 分支
git push -u origin main
```

推送后，GitHub Actions 会自动：
1. `ci.yml` → 运行测试 + Bandit 安全扫描 + 构建 Docker 镜像
2. `deploy.yml` → 构建并推送 GHCR 镜像 + 部署到 Staging + 冒烟测试

## 步骤 3：配置 GitHub Actions Secrets

仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名称 | 说明 | 示例 |
|-------------|------|------|
| `ACAS_SECRET_KEY_STAGING` | Staging JWT 密钥（32+ 随机字符） | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `ACAS_ENCRYPTION_KEY_STAGING` | Staging 加密密钥（Fernet key） | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `ACAS_DB_PASSWORD_STAGING` | Staging 数据库密码 | `acas_staging_db_2026` |
| `STAGING_HOST` | Staging 服务器 IP/域名 | `203.0.113.10` |
| `STAGING_USER` | Staging SSH 用户 | `ubuntu` |
| `SSH_KEY` | Staging SSH 私钥（ed25519） | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `DOMAIN` | Staging 域名（用于健康检查） | `staging.acas.example.com` |
| `ACAS_TEST_API_KEY` | Staging 测试 API Key | 可选，冒烟测试用 |

## 步骤 4：验证 CI/CD

推送后访问：https://github.com/<YOUR_GITHUB_USER>/acas-api/actions

应看到：
- ✅ CI 流水线：测试通过（覆盖率 ≥ 80%）、Bandit 无高危、Docker 镜像构建成功
- ✅ Deploy 流水线：镜像推送到 `ghcr.io/<YOUR_GITHUB_USER>/acas-api:staging`

## 步骤 5：本地 K8s 测试（可选）

如需本地 K8s（minikube/k3s）测试：

```powershell
# 加载本地镜像到 minikube
minikube image load acas:v2.0.0

# 部署
kubectl apply -k deploy/k8s/  # 或 kubectl apply -f deploy/k8s/
```

`deployment.yaml` 已配置 `image: ${ACR_REGISTRY:-acas}:v2.0.0`，本地使用 `acas:v2.0.0`。

生产环境覆盖：`ACR_REGISTRY=ghcr.io/<YOUR_GITHUB_USER>/acas-api kubectl apply -f deploy/k8s/deployment.yaml`

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| CI 测试失败 | 覆盖率 < 80% | 本地运行 `pytest --cov=src --cov-fail-under=80` 确认 |
| Bandit 失败 | 高危漏洞 | 检查 `bandit -r src/` 输出 |
| Deploy 失败 | Secret 缺失 | 确认步骤 3 所有 Secret 已配置 |
| 镜像拉取失败 | GHCR 未推送 | 确认 CI 的 Docker Build 步骤成功 |
| K8s Pod CrashLoop | Secret/ConfigMap 未应用 | `kubectl describe pod` 查看事件 |

## 当前 P0 阻塞项总结

1. **Git remote 未配置** → 按步骤 2 操作
2. **GitHub Actions Secrets 未配置** → 按步骤 3 操作
3. 覆盖率 80% ✅ 已达成
4. 容器内 ML 验证 ✅ 已通过
