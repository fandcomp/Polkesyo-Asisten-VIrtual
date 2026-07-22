"""Unit tests for RateLimiterService.is_admin_login_blocked / record_admin_login_failure.

Originally a single `check_admin_login_limit` that incremented on every request (2026-07-21) —
replaced same-day after that design locked out real admins: every request the frontend makes
carries the stored Basic-Auth header, so a single dashboard page load (several parallel
authenticated calls) burned through the 5-per-15-min budget in seconds even with a correct
password every time. Now split into a peek (`is_admin_login_blocked`, no increment) and an
explicit failure recorder (`record_admin_login_failure`), so only actual bad credentials count
against the budget. Mirrors test_redis_cache_service.py's AsyncMock-client pattern.
"""
import pytest
from unittest.mock import AsyncMock

from app.services.rate_limiter_service import RateLimiterService


def make_service_with_client() -> RateLimiterService:
    service = RateLimiterService()
    service.client = AsyncMock()
    return service


@pytest.mark.asyncio
class TestIsAdminLoginBlocked:
    async def test_no_client_fails_open(self):
        service = RateLimiterService()
        service.client = None
        assert await service.is_admin_login_blocked("1.2.3.4") is False

    async def test_no_prior_failures_not_blocked(self):
        service = make_service_with_client()
        service.client.get = AsyncMock(return_value=None)

        assert await service.is_admin_login_blocked("1.2.3.4") is False

    async def test_under_limit_not_blocked(self):
        service = make_service_with_client()
        service.client.get = AsyncMock(
            return_value=str(RateLimiterService.LIMIT_ADMIN_LOGIN_PER_WINDOW - 1).encode()
        )

        assert await service.is_admin_login_blocked("1.2.3.4") is False

    async def test_at_or_over_limit_blocked(self):
        service = make_service_with_client()
        service.client.get = AsyncMock(
            return_value=str(RateLimiterService.LIMIT_ADMIN_LOGIN_PER_WINDOW).encode()
        )

        assert await service.is_admin_login_blocked("1.2.3.4") is True

    async def test_peek_never_increments(self):
        service = make_service_with_client()
        service.client.get = AsyncMock(return_value=None)

        await service.is_admin_login_blocked("1.2.3.4")

        service.client.incr.assert_not_called()

    async def test_redis_error_fails_open(self):
        service = make_service_with_client()
        service.client.get = AsyncMock(side_effect=ConnectionError("redis down"))

        assert await service.is_admin_login_blocked("1.2.3.4") is False


@pytest.mark.asyncio
class TestRecordAdminLoginFailure:
    async def test_no_client_is_a_noop(self):
        service = RateLimiterService()
        service.client = None
        await service.record_admin_login_failure("1.2.3.4")  # must not raise

    async def test_first_failure_sets_expiry(self):
        service = make_service_with_client()
        service.client.incr = AsyncMock(return_value=1)
        service.client.expire = AsyncMock()

        await service.record_admin_login_failure("1.2.3.4")

        service.client.expire.assert_awaited_once_with(
            f"{RateLimiterService.PREFIX_ADMIN_LOGIN}1.2.3.4",
            RateLimiterService.ADMIN_LOGIN_WINDOW_SECONDS,
        )

    async def test_subsequent_failure_does_not_reset_expiry(self):
        service = make_service_with_client()
        service.client.incr = AsyncMock(return_value=2)
        service.client.expire = AsyncMock()

        await service.record_admin_login_failure("1.2.3.4")

        service.client.expire.assert_not_called()

    async def test_redis_error_does_not_raise(self):
        service = make_service_with_client()
        service.client.incr = AsyncMock(side_effect=ConnectionError("redis down"))

        await service.record_admin_login_failure("1.2.3.4")  # must not raise

    async def test_failures_reach_the_block_threshold(self):
        """Integration-style check across both methods: N recorded failures should make
        is_admin_login_blocked report True on the (N+1)th check."""
        service = make_service_with_client()
        count = {"n": 0}

        async def incr(key: str):
            count["n"] += 1
            return count["n"]

        service.client.incr = AsyncMock(side_effect=incr)
        service.client.expire = AsyncMock()
        service.client.get = AsyncMock(side_effect=lambda key: str(count["n"]).encode())

        for _ in range(RateLimiterService.LIMIT_ADMIN_LOGIN_PER_WINDOW):
            assert await service.is_admin_login_blocked("1.2.3.4") is False
            await service.record_admin_login_failure("1.2.3.4")

        assert await service.is_admin_login_blocked("1.2.3.4") is True
