"""
ACAS v2 - Test Configuration
Pytest fixtures and configuration

Key design decisions:
1. Python creates TWO separate module objects for the same physical file when
   imported via 'src.core.database' vs 'core.database' (different sys.path entries).
   We patch BOTH module instances' Database._session_factory so all routes see
   the test DB regardless of which import path they used.
2. Uses a file-based SQLite to avoid aiosqlite :memory: isolation issues on
   Windows across pytest-asyncio event loops.
3. Each test gets a fresh database file and fresh tables.
4. test_user/admin_user fixtures create users directly via the test engine.
   auth_headers performs a real login so JWT tokens are consistent.
"""

import asyncio
import os
import sys
import tempfile
from typing import AsyncGenerator, Generator

# Windows compatibility: use SelectorEventLoopPolicy to avoid ProactorEventLoop issues
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

# sys.path: project root ONLY. 'src' is a package, so 'from src.X' resolves.
# We intentionally do NOT add src/ to sys.path — that would also expose
# api/core/ml/sentiment as top-level packages and recreate the dual-module
# defect (same file imported as both 'src.api.models' and 'api.models').
project_root = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, project_root)

# MODELS ARE LOADED AUTOMATICALLY by importing src.api.main (see below).
# All routes import src.api.models which registers tables with Base.metadata.
# DO NOT import src.api.models directly here — it causes SQLAlchemy declarative registry
# to detect duplicate class definitions when the same file is loaded via two module names.

# ─────────────────────────────────────────────────────────────────────────────
# Disable ML components in tests — prevents model downloads and long init times.
# These must be set BEFORE config is imported, since config reads env vars at import.
# ─────────────────────────────────────────────────────────────────────────────
os.environ.setdefault("ACAS_ML_SENTIMENT_ENABLED", "false")
os.environ.setdefault("ACAS_ML_TIMESFM_ENABLED", "false")

# ─────────────────────────────────────────────────────────────────────────────
# Import order matters: load app (which imports routes → models → Base) FIRST.
# This registers all SQLAlchemy tables against the Base from src.core.database.
# ─────────────────────────────────────────────────────────────────────────────
from src.core.database import Base, db as _db
from src.core.config import config
from src.api.main import app

# Single Database instance (dual-module defect eliminated: all code now uses the
# 'src.' namespace, so 'src.core.database' is the only module object).
_orig_factory = _db._session_factory

# ─────────────────────────────────────────────────────────────────────────────
# Test database file (recreated fresh per test via StaticPool sharing)
# ─────────────────────────────────────────────────────────────────────────────
_TEST_DB_FILE = os.path.join(tempfile.gettempdir(), "acas_test.db")
_TEST_DB_URL = f"sqlite+aiosqlite:///{_TEST_DB_FILE.replace(chr(92), '/')}"


# ─────────────────────────────────────────────────────────────────────────────
# test_engine: function-scoped — one fresh DB per test.
# StaticPool ensures aiosqlite reuses the SAME connection across coroutines.
# NOTE: event_loop fixture removed — pytest-asyncio asyncio_mode="auto" manages
# the event loop automatically. Custom event_loop is deprecated and causes
# async fixtures to return coroutines instead of resolved values in full suite runs.
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture(scope="function")
async def test_engine() -> AsyncGenerator:
    # Delete stale DB file
    if os.path.exists(_TEST_DB_FILE):
        try:
            os.remove(_TEST_DB_FILE)
        except OSError:
            pass

    engine = create_async_engine(
        _TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    if os.path.exists(_TEST_DB_FILE):
        try:
            os.remove(_TEST_DB_FILE)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# db_session: patches BOTH Database instances' _session_factory with the test
# sessionmaker. This is the ONLY way to ensure all routes see the test DB —
# patching just one module leaves the other untouched (they are different objects).
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Patch BOTH Database instances and yield a real test session.

    Yielding the session is required because some tests use db_session directly
    (e.g., db_session.add(user)) and expect a non-None object.
    """
    test_sm = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Patch the single Database instance's session factory with the test session
    _db._session_factory = test_sm

    # Yield a real session for tests that use db_session directly
    async with test_sm() as session:
        yield session

    # Restore original factory
    _db._session_factory = _orig_factory


# ─────────────────────────────────────────────────────────────────────────────
# client: depends on db_session so patch is active before any HTTP request.
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────────────────
# Test data fixtures
# ─────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def test_user_data():
    return {
        "email": "test@example.com",
        "password": "TestPassword123!",
        "name": "Test User",
        "company": "Test Company",
    }


@pytest.fixture
def admin_user_data():
    return {
        "email": "admin@example.com",
        "password": "AdminPassword123!",
        "name": "Admin User",
        "company": "ACAS Inc",
    }


# ─────────────────────────────────────────────────────────────────────────────
# test_user / admin_user: create users directly via the test engine (bypasses
# FastAPI DI so they are guaranteed to exist before any endpoint is called).
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def test_user(test_engine, test_user_data) -> AsyncGenerator:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from src.core.security import password_manager
    from src.api.models import User

    sm = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with sm() as session:
        user = User(
            email=test_user_data["email"],
            name=test_user_data["name"],
            company=test_user_data["company"],
            hashed_password=password_manager.hash(test_user_data["password"]),
            role="user",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user


@pytest_asyncio.fixture
async def admin_user(test_engine, admin_user_data) -> AsyncGenerator:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from src.core.security import password_manager
    from src.api.models import User

    sm = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)
    async with sm() as session:
        user = User(
            email=admin_user_data["email"],
            name=admin_user_data["name"],
            company=admin_user_data["company"],
            hashed_password=password_manager.hash(admin_user_data["password"]),
            role="admin",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user


# ─────────────────────────────────────────────────────────────────────────────
# auth_headers: real login so JWT tokens are consistent with the test DB.
# ─────────────────────────────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user_data, test_user) -> dict:
    response = await client.post(
        "/auth/login",
        json={"email": test_user_data["email"], "password": test_user_data["password"]},
    )
    if response.status_code == 200:
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return {}


@pytest_asyncio.fixture
async def admin_auth_headers(client: AsyncClient, admin_user_data, admin_user) -> dict:
    response = await client.post(
        "/auth/login",
        json={"email": admin_user_data["email"], "password": admin_user_data["password"]},
    )
    if response.status_code == 200:
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return {}
