#!/usr/bin/env python3
"""Direct database test - bypass all config and connect directly"""
import asyncio
import sys
import asyncpg

async def test_direct():
    """Test direct connection to PostgreSQL"""
    # Try different connection parameters
    configs = [
        {"host": "localhost", "port": 5432, "user": "postgres", "password": "postgres", "database": "acas"},
        {"host": "localhost", "port": 5432, "user": "acas", "password": "acas", "database": "acas"},
        {"host": "127.0.0.1", "port": 5432, "user": "postgres", "password": "postgres", "database": "acas"},
    ]
    
    for i, cfg in enumerate(configs):
        print(f"\nTest {i+1}: {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['database']}")
        try:
            conn = await asyncpg.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"]
            )
            print(f"  SUCCESS: Connected!")
            
            # Check if users table exists
            result = await conn.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')")
            print(f"  Users table exists: {result}")
            
            await conn.close()
            return cfg  # Return working config
            
        except Exception as e:
            print(f"  FAILED: {e}")
    
    print("\nAll connection attempts failed!")
    return None

if __name__ == "__main__":
    working_cfg = asyncio.run(test_direct())
    if working_cfg:
        print(f"\nWorking config: {working_cfg}")
    sys.exit(0 if working_cfg else 1)
