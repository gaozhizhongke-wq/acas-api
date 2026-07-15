#!/usr/bin/env python3
"""Check tables in SQLite database"""
import sqlite3
import os

db_path = "acas.db"
if not os.path.exists(db_path):
    print(f"Database file not found: {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in {db_path}: {tables}")
    conn.close()
