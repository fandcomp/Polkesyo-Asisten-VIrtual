"""Unit tests for the two-admin-account identity/permission system (2026-07-21).

Primary admin (settings.admin_username/admin_password_hash) stays fully unrestricted
(evaluation_tabs=None). The second, reviewer-role admin (settings.second_admin_username/
second_admin_password_hash) is restricted to EVALUATION_TABS_SECOND_ADMIN via
require_evaluation_tab. Follows this repo's existing AsyncMock-rate-limiter test convention
(test_evaluation_scenario_admin.py) rather than hitting real Redis.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app.core import security
from app.core.security import (
    EVALUATION_TABS_SECOND_ADMIN,
    get_current_admin,
    require_admin_auth,
    require_evaluation_tab,
)

PRIMARY_PASSWORD = "primary-pw-for-tests"
SECOND_PASSWORD = "second-pw-for-tests"


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def _request(client_host: str = "10.0.0.1"):
    request = MagicMock()
    request.headers = {}
    request.client.host = client_host
    return request


def _allow_rate_limit():
    """Not-currently-blocked limiter double."""
    limiter = AsyncMock()
    limiter.is_admin_login_blocked = AsyncMock(return_value=False)
    limiter.record_admin_login_failure = AsyncMock()
    return patch("app.core.security.get_rate_limiter", AsyncMock(return_value=limiter))


def _tracking_limiter():
    """Same double, but returns the limiter mock directly (not wrapped in `with`) so callers can
    assert on record_admin_login_failure's call count afterward."""
    limiter = AsyncMock()
    limiter.is_admin_login_blocked = AsyncMock(return_value=False)
    limiter.record_admin_login_failure = AsyncMock()
    return limiter


@pytest.fixture(autouse=True)
def configured_admins(monkeypatch):
    monkeypatch.setattr(security.settings, "admin_username", "primary")
    monkeypatch.setattr(security.settings, "admin_password_hash", _hash(PRIMARY_PASSWORD))
    monkeypatch.setattr(security.settings, "second_admin_username", "reviewer")
    monkeypatch.setattr(security.settings, "second_admin_password_hash", _hash(SECOND_PASSWORD))


@pytest.mark.asyncio
class TestGetCurrentAdmin:
    async def test_primary_admin_is_unrestricted(self):
        creds = HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD)
        with _allow_rate_limit():
            admin = await get_current_admin(_request(), creds)
        assert admin.username == "primary"
        assert admin.evaluation_tabs is None

    async def test_second_admin_gets_restricted_tabs(self):
        creds = HTTPBasicCredentials(username="reviewer", password=SECOND_PASSWORD)
        with _allow_rate_limit():
            admin = await get_current_admin(_request(), creds)
        assert admin.username == "reviewer"
        assert admin.evaluation_tabs == EVALUATION_TABS_SECOND_ADMIN

    async def test_wrong_password_raises_401(self):
        creds = HTTPBasicCredentials(username="primary", password="not-the-password")
        with _allow_rate_limit():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_admin(_request(), creds)
        assert exc_info.value.status_code == 401

    async def test_unknown_username_raises_401(self):
        creds = HTTPBasicCredentials(username="nobody", password="whatever")
        with _allow_rate_limit():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_admin(_request(), creds)
        assert exc_info.value.status_code == 401

    async def test_second_admin_disabled_when_unset(self, monkeypatch):
        monkeypatch.setattr(security.settings, "second_admin_username", "")
        monkeypatch.setattr(security.settings, "second_admin_password_hash", "")
        creds = HTTPBasicCredentials(username="reviewer", password=SECOND_PASSWORD)
        with _allow_rate_limit():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_admin(_request(), creds)
        assert exc_info.value.status_code == 401

    async def test_unconfigured_primary_hash_raises_503(self, monkeypatch):
        monkeypatch.setattr(security.settings, "admin_password_hash", "")
        creds = HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD)
        with _allow_rate_limit():
            with pytest.raises(HTTPException) as exc_info:
                await get_current_admin(_request(), creds)
        assert exc_info.value.status_code == 503

    async def test_blocked_ip_raises_429_even_with_correct_credentials(self):
        limiter = AsyncMock()
        limiter.is_admin_login_blocked = AsyncMock(return_value=True)
        creds = HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD)
        with patch("app.core.security.get_rate_limiter", AsyncMock(return_value=limiter)):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_admin(_request(), creds)
        assert exc_info.value.status_code == 429

    async def test_successful_login_never_records_a_failure(self):
        """Regression test for the 2026-07-21 incident: a correct login (or several, as a real
        admin dashboard fires many authenticated requests per page load) must never increment
        the failure counter — only actual bad credentials may."""
        limiter = _tracking_limiter()
        creds = HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD)
        with patch("app.core.security.get_rate_limiter", AsyncMock(return_value=limiter)):
            for _ in range(10):  # well past the 5-attempt limit, all successful
                await get_current_admin(_request(), creds)
        limiter.record_admin_login_failure.assert_not_called()

    async def test_failed_login_records_a_failure(self):
        limiter = _tracking_limiter()
        creds = HTTPBasicCredentials(username="primary", password="wrong")
        with patch("app.core.security.get_rate_limiter", AsyncMock(return_value=limiter)):
            with pytest.raises(HTTPException):
                await get_current_admin(_request(), creds)
        limiter.record_admin_login_failure.assert_awaited_once_with("10.0.0.1")


@pytest.mark.asyncio
class TestRequireAdminAuth:
    async def test_returns_username_for_either_account(self):
        with _allow_rate_limit():
            primary = await require_admin_auth(
                await get_current_admin(_request(), HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD))
            )
            second = await require_admin_auth(
                await get_current_admin(_request(), HTTPBasicCredentials(username="reviewer", password=SECOND_PASSWORD))
            )
        assert primary == "primary"
        assert second == "reviewer"


@pytest.mark.asyncio
class TestRequireEvaluationTab:
    async def test_primary_admin_passes_any_tab(self):
        with _allow_rate_limit():
            admin = await get_current_admin(_request(), HTTPBasicCredentials(username="primary", password=PRIMARY_PASSWORD))
        checker = require_evaluation_tab("scenarios")
        result = await checker(admin)
        assert result is admin

    async def test_second_admin_passes_granted_tab(self):
        with _allow_rate_limit():
            admin = await get_current_admin(_request(), HTTPBasicCredentials(username="reviewer", password=SECOND_PASSWORD))
        for tab in EVALUATION_TABS_SECOND_ADMIN:
            checker = require_evaluation_tab(tab)
            assert await checker(admin) is admin

    async def test_second_admin_blocked_on_other_tab(self):
        with _allow_rate_limit():
            admin = await get_current_admin(_request(), HTTPBasicCredentials(username="reviewer", password=SECOND_PASSWORD))
        checker = require_evaluation_tab("scenarios")
        with pytest.raises(HTTPException) as exc_info:
            await checker(admin)
        assert exc_info.value.status_code == 403
