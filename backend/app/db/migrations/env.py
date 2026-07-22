"""Alembic environment configuration."""
import asyncio
import logging
import os
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine
from alembic import context

# Set Python path to include app
import sys
sys.path.insert(0, '/app')

from app.core.config import settings
from app.db.models import Base

# Alembic Config object
config = context.config

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("alembic.env")

# Metadata for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (without database connection)."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Execute migrations given async connection context."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async connection."""
    url = settings.database_url
    logger.info(f"Connecting to database: {url[:50]}...")

    connectable: AsyncEngine = create_async_engine(
        url,
        poolclass=pool.NullPool,
        echo=False,
        future=True,
    )

    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with event loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_async_migrations())
    else:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, run_async_migrations())
            future.result()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()