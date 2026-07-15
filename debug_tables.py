"""Debug table registration in models.py"""
import sys, os

# Set up path
_root = r"C:\Users\HUAWEI\.qclaw\workspace-agent-eb98a2a2\acas-v2"
sys.path.insert(0, os.path.join(_root, "src"))
sys.path.insert(0, _root)

# Patch MetaData.tables setter BEFORE any import
import sqlalchemy.sql.schema
_original_tables = dict(sqlalchemy.sql.schema.MetaData.tables)

def tracking_set_tables(self, name, table):
    import traceback
    stack = traceback.extract_stack()
    print(f"  add_table: name={name}")
    for f in stack[-8:]:
        if any(x in f.filename for x in ["models.py", "database.py", "decl_", "orm"]):
            print(f"    {f.filename}:{f.lineno} in {f.name}")
    print()
    _original_tables[name] = table

sqlalchemy.sql.schema.MetaData.tables = property(
    lambda self: _original_tables,
    tracking_set_tables
)

# Now do the import
print("=== Step 1: Import Base from src.core.database ===")
from src.core.database import Base
print(f"Base id: {id(Base)}")
print(f"Base.metadata id: {id(Base.metadata)}")
print(f"Base.registry id: {id(Base.registry)}")
print(f"Tables so far: {list(Base.metadata.tables.keys())}")

print()
print("=== Step 2: Check if models.py already imported ===")
print(f"'src.api.models' in sys.modules: {'src.api.models' in sys.modules}")

print()
print("=== Step 3: Import src.api.models ===")
try:
    import src.api.models
    print(f"SUCCESS! Tables: {list(Base.metadata.tables.keys())}")
except Exception as e:
    print(f"FAILED: {e}")
    import traceback
    traceback.print_exc()
