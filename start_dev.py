#!/usr/bin/env python3
"""
ACAS v2 - 本地开发启动脚本 (无需 Docker)
使用 SQLite + 内存缓存，适合快速开发和测试
"""

import os
import sys
import asyncio
from pathlib import Path

# 设置环境变量
os.environ["ACAS_ENVIRONMENT"] = "development"
os.environ["ACAS_DEBUG"] = "true"
os.environ["ACAS_SECRET_KEY"] = "dev-secret-key-change-in-production-min-32-chars"
os.environ["ACAS_DB_URL"] = "sqlite+aiosqlite:///./acas_dev.db"
os.environ["ACAS_REDIS_URL"] = "memory://"  # 使用内存缓存
os.environ["ACAS_RL_ENABLED"] = "false"  # 开发环境关闭限流
os.environ["ACAS_API_HOST"] = "0.0.0.0"
os.environ["ACAS_API_PORT"] = "8000"
os.environ["ACAS_MON_LOG_LEVEL"] = "DEBUG"

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from api.main import app
import uvicorn


def main():
    print("=" * 60)
    print("ACAS v2 - 本地开发模式")
    print("=" * 60)
    print()
    print("配置:")
    print(f"  数据库: SQLite (acas_dev.db)")
    print(f"  缓存: 内存")
    print(f"  限流: 已禁用")
    print(f"  日志级别: DEBUG")
    print()
    print("服务地址:")
    print(f"  API:        http://localhost:8000")
    print(f"  健康检查:   http://localhost:8000/health")
    print(f"  API 文档:   http://localhost:8000/docs")
    print()
    print("按 Ctrl+C 停止服务")
    print("=" * 60)
    print()
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
