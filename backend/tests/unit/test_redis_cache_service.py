"""Unit tests for RedisCacheService.invalidate_retrieval_cache.

Approving a chunk now triggers indexing automatically (routes_chunk_review.py), but the
1-hour vector/graph retrieval cache (redis_cache_service.py) is keyed by hashed query text,
not document_id, so the existing invalidate_document() can't target it. This covers the new
invalidate_retrieval_cache() method that clears the whole retrieval-cache namespace instead.
"""
import pytest
from unittest.mock import AsyncMock

from app.services.redis_cache_service import RedisCacheService


def make_service_with_client(scan_pages: list[tuple[int, list[bytes]]]) -> RedisCacheService:
    """Build a RedisCacheService with a fake async client whose `scan` yields the given
    (next_cursor, keys) pages in order, one call per prefix scanned."""
    service = RedisCacheService()
    client = AsyncMock()
    client.scan = AsyncMock(side_effect=scan_pages)
    client.delete = AsyncMock(return_value=0)
    service.client = client
    return service


@pytest.mark.asyncio
class TestInvalidateRetrievalCache:
    async def test_no_client_returns_zero(self):
        service = RedisCacheService()
        service.client = None
        assert await service.invalidate_retrieval_cache() == 0

    async def test_deletes_keys_found_under_both_prefixes(self):
        # One page per prefix (vector:, graph:), each with keys to delete, cursor 0 ends the scan.
        service = make_service_with_client(
            [
                (0, [b"vector:general:abc"]),
                (0, [b"graph:general:def"]),
            ]
        )
        service.client.delete = AsyncMock(return_value=1)

        deleted = await service.invalidate_retrieval_cache()

        assert deleted == 2
        assert service.client.delete.await_count == 2

    async def test_no_matching_keys_deletes_nothing(self):
        service = make_service_with_client([(0, []), (0, [])])

        deleted = await service.invalidate_retrieval_cache()

        assert deleted == 0
        service.client.delete.assert_not_called()

    async def test_redis_error_is_swallowed_and_returns_zero(self):
        service = RedisCacheService()
        client = AsyncMock()
        client.scan = AsyncMock(side_effect=ConnectionError("redis down"))
        service.client = client

        assert await service.invalidate_retrieval_cache() == 0
