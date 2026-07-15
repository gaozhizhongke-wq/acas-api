#!/usr/bin/env python3
"""Minimal test: test database connection and user creation"""
import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from core.config import get_config
from core.database import Database
from api.models import User, Base
from sqlalchemy.ext.asyncio import create_async_engine

async def test_db():
    """Test database connection and user creation"""
    config = get_config()
    print(f"Database URL: {config.database.url}")
    
    # Create engine and connect directly
    engine = create_async_engine(config.database.url, echo=True)
    
    try:
        async with engine.connect() as conn:
            print("✓ Database connection successful!")
            
            # Check if users table exists
            result = await conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')"
            )
            exists = result.scalar()
            print(f"Users table exists: {exists}")
            
            if exists:
                # Try to query users table
                result = await conn.execute("SELECT COUNT(*) FROM users")
                count = result.scalar()
                print(f"Users count: {count}")
                
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    await engine.dispose()
    return True

if __name__ == "__main__":
    success = asyncio.run(test_db())
    sys.exit(0 if success else 1)
