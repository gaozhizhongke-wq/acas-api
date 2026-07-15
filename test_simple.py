#!/usr/bin/env python3
"""Simple test: read .env and test database connection"""
import asyncio
import os
from pathlib import Path

# Read .env file
env_file = Path(__file__).parent / ".env"
env_vars = {}
if env_file.exists():
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key] = value
                # Also set as environment variable
                os.environ[key] = value

# Print database URL
db_url = env_vars.get('ACAS_DB_URL') or os.environ.get('ACAS_DB_URL')
print(f"Database URL from .env: {db_url}")

# Try to connect using asyncpg directly
import asyncpg

async def test_conn():
    # Parse URL (simple parsing)
    # Format: postgresql+asyncpg://user:password@host:port/database
    url = db_url
    if '//' in url:
        url = url.split('//')[1]
    user_pass, host_db = url.split('@')
    user, password = user_pass.split(':')
    host_port, database = host_db.split('/')
    host, port = host_port.split(':')
    port = int(port)
    
    print(f"\nTrying to connect:")
    print(f"  Host: {host}")
    print(f"  Port: {port}")
    print(f"  User: {user}")
    print(f"  Database: {database}")
    
    try:
        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        print("  SUCCESS: Connected!")
        
        # Check if users table exists
        result = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users')"
        )
        print(f"  Users table exists: {result}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"  FAILED: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_conn())
    exit(0 if success else 1)
