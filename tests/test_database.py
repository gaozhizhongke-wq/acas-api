"""
ACAS v2 - Database Layer Coverage Tests
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio


class TestDatabase:
    """Test Database class"""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """test_initialize_success - mock create_async_engine"""
        from src.core.database import Database

        db = Database()
        assert db._engine is None
        assert db._session_factory is None

        mock_engine = MagicMock()
        mock_session_maker = MagicMock()

        with patch("src.core.database.create_async_engine", return_value=mock_engine) as mock_create:
            with patch("src.core.database.async_sessionmaker", return_value=mock_session_maker) as mock_sm:
                await db.initialize()

                mock_create.assert_called_once()
                call_kwargs = mock_create.call_args.kwargs
                assert call_kwargs["echo"] is False
                mock_sm.assert_called_once()

        assert db._engine is mock_engine
        assert db._session_factory is mock_session_maker

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        """Calling initialize twice does not recreate the engine"""
        from src.core.database import Database

        db = Database()
        mock_engine = MagicMock()

        with patch("src.core.database.create_async_engine", return_value=mock_engine):
            with patch("src.core.database.async_sessionmaker"):
                await db.initialize()
                first_engine = db._engine
                await db.initialize()
                assert db._engine is first_engine

    @pytest.mark.asyncio
    async def test_close(self):
        """test_close - mock engine dispose"""
        from src.core.database import Database

        db = Database()
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()
        db._engine = mock_engine
        db._session_factory = MagicMock()

        await db.close()

        mock_engine.dispose.assert_called_once()
        assert db._engine is None
        assert db._session_factory is None

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        """Closing when not initialized should be safe (no-op)"""
        from src.core.database import Database

        db = Database()
        await db.close()
        assert db._engine is None

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """test_health_check - mock return scalar"""
        from src.core.database import Database

        db = Database()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()
        # connect() is used as async ctx mgr: async with engine.connect() as conn
        mock_engine.connect = MagicMock(return_value=mock_conn)
        db._engine = mock_engine

        result = await db.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_no_engine(self):
        """Health check returns False when engine is None"""
        from src.core.database import Database

        db = Database()
        result = await db.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_exception(self):
        """Health check returns False on exception"""
        from src.core.database import Database

        db = Database()
        mock_engine = MagicMock()
        # connect() must return an object where __aenter__ raises on await
        class RaiseOnEnter:
            async def __aenter__(self):
                raise Exception("connection refused")
            async def __aexit__(self, *args):
                pass
            def execute(self, *args, **kwargs):
                raise Exception("never called")

        mock_engine.connect = MagicMock(return_value=RaiseOnEnter())
        db._engine = mock_engine

        result = await db.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_create_tables_no_engine(self):
        """create_tables with no engine does nothing"""
        from src.core.database import Database

        db = Database()
        db._engine = None
        await db.create_tables()

    @pytest.mark.asyncio
    async def test_create_tables_with_tables(self):
        """test_create_tables - mock run_sync"""
        from src.core.database import Database
        from src.core import database as db_module

        db = Database()
        mock_engine = MagicMock()
        mock_sync_conn = MagicMock()

        async def mock_run_sync(fn):
            fn(mock_sync_conn)

        mock_conn_ctx = MagicMock()
        mock_conn_ctx.run_sync = mock_run_sync
        mock_engine.begin = AsyncMock(return_value=mock_conn_ctx)
        db._engine = mock_engine

        mock_cfg = MagicMock()
        mock_cfg.is_production = False
        mock_cfg.environment = "development"

        with patch.object(db_module, "config", mock_cfg):
            with patch.object(db_module.Base.metadata, "tables", {}):
                await db.create_tables()

    @pytest.mark.asyncio
    async def test_create_tables_production_forbidden(self):
        """create_tables raises in production"""
        from src.core.database import Database
        from src.core import database as db_module

        db = Database()
        db._engine = MagicMock()

        mock_cfg = MagicMock()
        mock_cfg.is_production = True

        with patch.object(db_module, "config", mock_cfg):
            with pytest.raises(RuntimeError, match="production"):
                await db.create_tables()

    @pytest.mark.asyncio
    async def test_drop_tables(self):
        """drop_tables calls Base.metadata.drop_all"""
        from src.core.database import Database
        from src.core import database as db_module

        db = Database()
        mock_sync_conn = MagicMock()

        # Custom async ctx manager; run_sync must be async (awaited by code)
        class AsyncCtx:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def run_sync(self, fn):
                fn(mock_sync_conn)

        mock_engine = MagicMock()
        mock_engine.begin = MagicMock(return_value=AsyncCtx())
        db._engine = mock_engine

        mock_cfg = MagicMock()
        mock_cfg.is_production = False

        with patch.object(db_module, "config", mock_cfg):
            await db.drop_tables()

    @pytest.mark.asyncio
    async def test_drop_tables_production_forbidden(self):
        """drop_tables raises in production"""
        from src.core.database import Database
        from src.core import database as db_module

        db = Database()

        mock_cfg = MagicMock()
        mock_cfg.is_production = True

        with patch.object(db_module, "config", mock_cfg):
            with pytest.raises(RuntimeError, match="production"):
                await db.drop_tables()
