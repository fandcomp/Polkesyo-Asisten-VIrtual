"""Redis cache service for retrieval results, ACIF scores, and FAQ answers."""
import json
import logging
import os
from datetime import timedelta
from typing import Any, Optional

try:
    import redis.asyncio as aioredis
except ImportError:
    import aioredis

logger = logging.getLogger(__name__)


class RedisCacheService:
    """Cache management for high-traffic endpoints."""

    # Cache TTLs (in seconds)
    TTL_VECTOR_RETRIEVAL = 3600  # 1 hour
    TTL_GRAPH_RETRIEVAL = 3600   # 1 hour
    TTL_ACIF_SCORE = 1800        # 30 minutes
    TTL_FAQ = 86400              # 24 hours
    TTL_ANSWER = 300             # 5 minutes

    # Cache key prefixes
    PREFIX_VECTOR = "vector:"
    PREFIX_GRAPH = "graph:"
    PREFIX_ACIF = "acif:"
    PREFIX_FAQ = "faq:"
    PREFIX_ANSWER = "answer:"

    def __init__(self):
        """Initialize Redis connection."""
        self.redis_url = os.environ.get(
            "REDIS_URL",
            "redis://localhost:6379/0"
        )
        self.client: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self.client = await aioredis.from_url(self.redis_url)
            await self.client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.client = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")

    async def get_vector_retrieval(
        self,
        query: str,
        intent: str = "general",
        top_k: int | None = None,
    ) -> Optional[list[dict]]:
        """Get cached vector retrieval results.

        `top_k` must match what the caller will request — otherwise a cache entry written
        for one top_k (e.g. a narrow-pool question) gets served to a later call requesting
        a different top_k for the same query text, silently truncating or under-filling the
        candidate pool for that later call. Kept optional (default None -> "unspecified"
        bucket) so any pre-existing caller that genuinely doesn't vary top_k still works,
        but every caller that does vary it (MultiQueryRetriever) must pass it explicitly.
        """
        if not self.client:
            return None

        cache_key = f"{self.PREFIX_VECTOR}{intent}:{top_k}:{self._hash_query(query)}"

        try:
            cached = await self.client.get(cache_key)
            if cached:
                logger.debug(f"Vector cache hit: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Vector cache retrieval failed: {e}")

        return None

    async def set_vector_retrieval(
        self,
        query: str,
        results: list[dict],
        intent: str = "general",
        top_k: int | None = None,
    ) -> bool:
        """Cache vector retrieval results (see get_vector_retrieval on `top_k`)."""
        if not self.client:
            return False

        cache_key = f"{self.PREFIX_VECTOR}{intent}:{top_k}:{self._hash_query(query)}"

        try:
            await self.client.setex(
                cache_key,
                self.TTL_VECTOR_RETRIEVAL,
                json.dumps(results)
            )
            logger.debug(f"Vector cached: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"Vector cache set failed: {e}")
            return False

    async def get_acif_score(
        self,
        chunk_id: str,
        query_hash: str = ""
    ) -> Optional[dict]:
        """Get cached ACIF score for chunk.

        Gate 2 scores depend on the query (intent match, expansions), so callers should
        pass a short query hash — a bare chunk_id key would serve one query's score to
        every other query for TTL_ACIF_SCORE.
        """
        if not self.client:
            return None

        cache_key = f"{self.PREFIX_ACIF}{chunk_id}:{query_hash}" if query_hash else f"{self.PREFIX_ACIF}{chunk_id}"

        try:
            cached = await self.client.get(cache_key)
            if cached:
                logger.debug(f"ACIF cache hit: {cache_key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"ACIF cache retrieval failed: {e}")

        return None

    async def set_acif_score(
        self,
        chunk_id: str,
        score_result: dict,
        query_hash: str = ""
    ) -> bool:
        """Cache ACIF score (see get_acif_score on query_hash)."""
        if not self.client:
            return False

        cache_key = f"{self.PREFIX_ACIF}{chunk_id}:{query_hash}" if query_hash else f"{self.PREFIX_ACIF}{chunk_id}"

        try:
            await self.client.setex(
                cache_key,
                self.TTL_ACIF_SCORE,
                json.dumps(score_result)
            )
            logger.debug(f"ACIF score cached: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"ACIF cache set failed: {e}")
            return False

    async def invalidate_document(self, document_id: str) -> int:
        """Invalidate all caches for a document when it's updated."""
        if not self.client:
            return 0

        try:
            # Find all keys containing this document
            pattern = f"*{document_id}*"
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await self.client.scan(
                    cursor,
                    match=pattern,
                    count=100
                )

                if keys:
                    deleted += await self.client.delete(*keys)

                if cursor == 0:
                    break

            logger.info(f"Invalidated {deleted} cache entries for document {document_id}")
            return deleted

        except Exception as e:
            logger.warning(f"Cache invalidation failed: {e}")
            return 0

    async def invalidate_retrieval_cache(self) -> int:
        """Clear all cached vector/graph retrieval results.

        Called right after indexing so a question asked before the underlying content was
        approved+indexed doesn't stay stuck on a stale cached miss for up to
        TTL_VECTOR_RETRIEVAL/TTL_GRAPH_RETRIEVAL (1 hour) after the content becomes available.
        Cache keys are hashed by query text, not document_id, so `invalidate_document` above
        can't target them — this clears the whole retrieval-cache namespace instead, which is
        acceptable since indexing is an infrequent admin action, not a hot path.
        """
        if not self.client:
            return 0

        deleted = 0
        try:
            for prefix in (self.PREFIX_VECTOR, self.PREFIX_GRAPH):
                cursor = 0
                while True:
                    cursor, keys = await self.client.scan(cursor, match=f"{prefix}*", count=100)
                    if keys:
                        deleted += await self.client.delete(*keys)
                    if cursor == 0:
                        break

            logger.info(f"Invalidated {deleted} retrieval cache entries")
            return deleted

        except Exception as e:
            logger.warning(f"Retrieval cache invalidation failed: {e}")
            return 0

    async def get_health(self) -> dict:
        """Check Redis health."""
        if not self.client:
            return {"status": "disconnected"}

        try:
            await self.client.ping()
            info = await self.client.info()
            return {
                "status": "ok",
                "used_memory": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _hash_query(query: str) -> str:
        """Create hash of query for cache key."""
        import hashlib
        return hashlib.md5(query.lower().encode()).hexdigest()


# Global instance
_cache_service: Optional[RedisCacheService] = None


async def get_cache_service() -> RedisCacheService:
    """Get or create cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = RedisCacheService()
        await _cache_service.connect()
    return _cache_service


async def close_cache_service() -> None:
    """Close cache service."""
    global _cache_service
    if _cache_service:
        await _cache_service.disconnect()
        _cache_service = None
