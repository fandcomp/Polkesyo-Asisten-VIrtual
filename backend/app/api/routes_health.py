import asyncio

import asyncpg
import redis.asyncio as aioredis
from fastapi import APIRouter
from neo4j import AsyncGraphDatabase

from app.core.config import settings

router = APIRouter()

CHROMA_HEALTH_TIMEOUT_SECONDS = 3
NEO4J_HEALTH_TIMEOUT_SECONDS = 3


async def _check_postgres() -> str:
    """Check PostgreSQL connectivity."""
    try:
        # Convert asyncpg URL to standard postgresql URL for connection string
        url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(url, timeout=3)
        await conn.execute("SELECT 1")
        await conn.close()
        return "ok"
    except Exception:
        return "error"


async def _check_redis() -> str:
    """Check Redis connectivity."""
    try:
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=3)
        await client.ping()
        await client.aclose()
        return "ok"
    except Exception:
        return "error"


def _chroma_heartbeat_sync() -> None:
    """Blocking Chroma call — chromadb's client is sync-only, so this must run
    in a worker thread (see the caller) instead of the event loop directly.

    Reuses the process-wide client: constructing a fresh HttpClient here leaked one
    TCP connection per 30s healthcheck until the worker exhausted its fd limit."""
    from app.services.vector_index_service import VectorIndexService

    VectorIndexService.get_chroma_client().heartbeat()


async def _check_chroma() -> str:
    """Check Chroma vector DB connectivity.

    chromadb.HttpClient has no timeout of its own, and calling it directly from an
    async def blocks the *entire event loop* of this worker — not just this request
    — if Chroma is slow or wedged (a known-flaky dependency here). Offload to a
    thread and bound it with asyncio.wait_for so a stuck Chroma degrades this one
    health check instead of freezing every other in-flight request on the worker.
    """
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_chroma_heartbeat_sync),
            timeout=CHROMA_HEALTH_TIMEOUT_SECONDS,
        )
        return "ok"
    except Exception:
        return "error"


async def _check_neo4j_unbounded() -> None:
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password),
    )
    try:
        async with driver.session() as session:
            await session.run("RETURN 1")
    finally:
        await driver.close()


async def _check_neo4j() -> str:
    """Check Neo4j graph DB connectivity.

    Unlike the other three checks, this previously had no timeout of its own — a
    wedged Neo4j connection (network hiccup, driver hang) could block this `await`
    forever. Since /health awaits each check sequentially, that would freeze every
    subsequent /health call on the worker (the same failure mode already guarded
    against for Chroma above), silently taking the whole worker off the health
    check's radar until someone notices and restarts it by hand.
    """
    try:
        await asyncio.wait_for(_check_neo4j_unbounded(), timeout=NEO4J_HEALTH_TIMEOUT_SECONDS)
        return "ok"
    except Exception:
        return "error"


@router.get("/health")
async def health():
    """Health check endpoint — verifies all required services are running."""
    services = {
        "postgres": await _check_postgres(),
        "redis": await _check_redis(),
        "chroma": await _check_chroma(),
        "neo4j": await _check_neo4j(),
    }
    overall = "ok" if all(v == "ok" for v in services.values()) else "degraded"
    return {"status": overall, "services": services}
