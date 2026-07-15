# ACAS v2 - API Package
"""RESTful API endpoints and models"""

# NOTE: Do NOT import `app` here.
# Importing app triggers main.py → routes → models, which creates a circular
# import that breaks Alembic migrations. Import src.api.main.app directly instead.

__all__ = []
