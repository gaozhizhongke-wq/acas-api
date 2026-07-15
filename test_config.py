#!/usr/bin/env python3
"""Test script: check if .env is read correctly"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from core.config import config

print(f"DATABASE URL FROM CONFIG: {config.database.url}")
print(f"IS PRODUCTION: {config.is_production}")
print(f"ENVIRONMENT: {config.environment}")
