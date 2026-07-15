#!/usr/bin/env python3
"""Create all tables in SQLite database"""
import sys
import os
import asyncio

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from core.config import config
from core.database import Base, Database
from src.models.user import User
from src.models.api_key import APIKey
from src.models.refresh_token import RefreshToken
from src.models.analysis_history import AnalysisHistory

async def create_tables():
    """Create all tables"""
    # Initialize database
    db = Database()
    await db.initialize()
    
    # Create all tables
    async with db._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print("Tables created successfully!")
    
    # Close connection
    await db.close()

if __name__ == "__main__":
    asyncio.run(create_tables())
