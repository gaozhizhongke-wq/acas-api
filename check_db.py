#!/usr/bin/env python3
"""Check database connection and create tables if needed"""
import asyncio
import sys

# Add src to path
sys.path.insert(0, "C:/Users/HUAWEI/.qclaw/workspace-agent-eb98a2a2/acas-v2/src")

from core.config import config
from core.database import db, get_db_session, Base
from sqlalchemy import text


async def check_and_create():
    """Check database connection and create tables"""
    print(f"Database URL: {config.database.url}")
    
    try:
        # Try to connect
        print("Connecting to database...")
        await db.initialize()
        print("SUCCESS: Database connection successful")
        
        # Create tables
        print("\nCreating tables...")
        await db.create_tables()
        print("SUCCESS: Tables created successfully!")
        
        # Verify tables exist
        async with get_db_session() as session:
            try:
                result = await session.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                print(f"SUCCESS: Users table exists, count: {count}")
            except Exception as e:
                print(f"ERROR: Users table check failed: {e}")
                return False
        
        await db.close()
        
    except Exception as e:
        print(f"ERROR: Database error: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(check_and_create())
    sys.exit(0 if success else 1)
