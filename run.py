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

# Add project root to sys.path so 'src' is importable as a package.
# Only 'src.' namespace is used (src.api.main, src.core.database, ...).
# Adding 'src' itself to sys.path would also expose core/api/ml/sentiment as
# top-level packages and create a duplicate-module defect.
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Explicitly load .env from project root before any config imports
from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

# Now import and run the app
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
