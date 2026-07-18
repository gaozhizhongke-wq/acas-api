"""
ACAS v2 - Database Layer
SQLAlchemy 2.0 async with connection pooling
"""

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text

from .config import config
from .logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base"""
    pass


class Database:
    """Async database manager"""

    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    async def initialize(self) -> None:
        """Initialize database connection"""
        if self._engine is not None:
            return

        # SQLite doesn't support pool_size and max_overflow
        engine_kwargs = {"echo": config.database.echo}
        if not config.database.url.startswith("sqlite"):
            engine_kwargs["pool_size"] = config.database.pool_size
            engine_kwargs["max_overflow"] = config.database.max_overflow

        # Pass SSL mode to the driver when configured
        connect_args: dict = {}
        if config.database.ssl_mode != "disable":
            connect_args["ssl"] = config.database.ssl_mode

        self._engine = create_async_engine(
            config.database.url,
            connect_args=connect_args,
            **engine_kwargs
        )

        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

        logger.info(f"Database connection initialized with URL: {config.database.url}")

    async def close(self) -> None:
        """Close database connection"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection closed")

    async def health_check(self) -> bool:
        """Check database connectivity"""
        if not self._engine:
            logger.error("Database health check: engine is None")
            return False

        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.exception(f"Database health check failed: {e}")
            return False

    async def create_tables(self, force: bool = False) -> None:
        """Create all tables (development only)
        If force=True, drops and recreates all tables.
        """
        if config.is_production:
            raise RuntimeError("create_tables() should not be used in production. Use Alembic migrations.")

        # Collect all table names
        all_tables = sorted(Base.metadata.tables.keys())
        if not all_tables:
            logger.warning("No tables found in Base.metadata. Models may not be imported.")
            return

        if force:
            for table_name in all_tables:
                try:
                    async with self._engine.begin() as conn:
                        await conn.execute(text(f'DROP TABLE IF EXISTS {table_name} CASCADE'))
                    logger.info(f"Dropped table: {table_name}")
                except Exception as e:
                    logger.warning(f"Failed to drop table {table_name}: {e}")

        # Create tables in dependency order: users first, then others
        creation_order = ['users'] + [t for t in all_tables if t != 'users']
        created = 0
        failed = []
        for table_name in creation_order:
            try:
                async with self._engine.begin() as conn:
                    await conn.run_sync(
                        lambda sync_conn, tn=table_name: Base.metadata.tables[tn].create(sync_conn, checkfirst=True)
                    )
                created += 1
                logger.info(f"Created table: {table_name}")
            except Exception as e:
                failed.append((table_name, str(e)))
                logger.warning(f"Failed to create table {table_name}: {e}")

        logger.info(f"Database table creation: {created}/{len(all_tables)} created, {len(failed)} failed")
        if failed:
            for name, err in failed:
                logger.error(f"  Failed: {name}: {err[:200]}")

    async def drop_tables(self) -> None:
        """Drop all tables (development/testing only)"""
        if config.is_production:
            raise RuntimeError("drop_tables() is disabled in production")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.info("Database tables dropped")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting database session"""
    if db._session_factory is None:
        await db.initialize()

    async with db._session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Global instance
db = Database()
