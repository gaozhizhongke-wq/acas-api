#!/usr/bin/env python3
"""
ACAS v2 - Application Entry Point
Fixes module import issues by adding src directory to sys.path
"""

import sys
import os
import platform
from pathlib import Path

# Windows: use SelectorEventLoop for psycopg async compatibility
if platform.system() == "Windows":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Add project root and src directory to sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Explicitly load .env from project root before any config imports
from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

# Now import and run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
