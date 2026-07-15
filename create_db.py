#!/usr/bin/env python3
"""Create database if not exists"""
import asyncio
import sys

# Add src to path
sys.path.insert(0, "C:/Users/HUAWEI/.qclaw/workspace-agent-eb98a2a2/acas-v2/src")

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def create_database():
    """Create database if not exists"""
    # Connect to default postgres database
    default_url = "postgresql+psycopg://acas:acas@localhost:5432/postgres"
    engine = create_async_engine(default_url)
    
    try:
        async with engine.connect() as conn:
            # Check if database exists
            result = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'acas'")
            )
            exists = result.scalar() is not None
            
            if not exists:
                print("Database 'acas' does not exist. Creating...")
                # Create database (can't use parameterized queries for CREATE DATABASE)
                await conn.execute(text("CREATE DATABASE acas"))
                print("SUCCESS: Database 'acas' created!")
            else:
                print("SUCCESS: Database 'acas' already exists")
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False
    finally:
        await engine.dispose()
    
    return True


if __name__ == "__main__":
    success = asyncio.run(create_database())
    sys.exit(0 if success else 1)
