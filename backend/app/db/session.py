"""Database session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.db.models import Base

# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=3600,
)

# Create session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Get database session for dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# Additive columns on tables that already exist in deployed databases. create_all only
# creates missing TABLES — it never ALTERs an existing one — so new columns must be added
# here idempotently (both dev and prod schemas are created by this function, not alembic).
_ADDITIVE_COLUMNS: tuple[str, ...] = (
    "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS rewritten_queries JSON",
    "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS detected_terms JSON",
    "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS expanded_terms JSON",
    "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS intent VARCHAR(50)",
    "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS intent_confidence FLOAT",
    (
        "ALTER TABLE chat_evaluation_logs ADD COLUMN IF NOT EXISTS "
        "clarification_used BOOLEAN NOT NULL DEFAULT false"
    ),
    "ALTER TABLE asq_responses ADD COLUMN IF NOT EXISTS condition_code VARCHAR(50)",
    "ALTER TABLE evaluation_results ADD COLUMN IF NOT EXISTS hit_rate_at_3 FLOAT",
)


async def init_db() -> None:
    """Initialize database tables."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        # Enable uuid-ossp extension for PostgreSQL
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";"))
        except Exception:
            pass  # Extension might already exist

        # Create all tables from models
        await conn.run_sync(Base.metadata.create_all)

    for statement in _ADDITIVE_COLUMNS:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(statement))
        except Exception:
            # Non-Postgres dev DBs (no IF NOT EXISTS support) skip harmlessly — the
            # column already exists there via create_all on the current models.
            pass