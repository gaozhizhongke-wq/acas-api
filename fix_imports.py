#!/usr/bin/env python3
"""Normalize all internal imports to the 'src.' namespace to eliminate the
dual-module (core.database vs src.core.database) defect.

Replaces:
  from core.      -> from src.core.
  from api.       -> from src.api.
  from ml.        -> from src.ml.
  from sentiment. -> from src.sentiment.
  import core.    -> import src.core.   (rare)
  import api.     -> import src.api.
  import ml.      -> import src.ml.
  import sentiment. -> import src.sentiment.
"""
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))

# Directories to process (source code + tests). Only bare 'core./api./ml./sentiment.'
# imports are rewritten; 'src.' prefixed imports are left untouched.
TARGET_DIRS = [os.path.join(ROOT, "src"), os.path.join(ROOT, "alembic"),
               os.path.join(ROOT, "tests")]

PATTERNS = [
    (r"(\bfrom\s+)(core|api|ml|sentiment)(\.\w)", r"\1src.\2\3"),
    (r"(\bimport\s+)(core|api|ml|sentiment)(\.\w)", r"\1src.\2\3"),
]

compiled = [(re.compile(p), r) for p, r in PATTERNS]

# Files to skip (already correct / not relevant)
SKIP = {"fix_imports.py"}
changed_files = []


def process_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    original = content
    for rx, repl in compiled:
        content = rx.sub(repl, content)
    if content != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        changed_files.append(path)


for base in TARGET_DIRS:
    for dirpath, dirnames, filenames in os.walk(base):
        # Skip the weird brace directory if present
        dirnames[:] = [d for d in dirnames if not d.startswith("{")]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            if fn in SKIP:
                continue
            process_file(os.path.join(dirpath, fn))

print(f"Changed {len(changed_files)} files:")
for f in changed_files:
    print("  ", os.path.relpath(f, ROOT))
