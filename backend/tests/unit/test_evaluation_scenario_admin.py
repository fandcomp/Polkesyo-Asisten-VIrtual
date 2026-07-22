"""Unit tests for evaluation scenario admin CRUD and the public-endpoint IP rate limit."""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import routes_evaluation_admin as admin_routes
from app.api.routes_evaluation_public import enforce_ip_rate_limit
from app.db.models import EvaluationScenario


def _db_returning(scalar=None, scalars_list=None):
    """AsyncMock db whose execute() resolves to the given scalar / scalars().all() list."""
    db = AsyncMock()
    db.add = MagicMock()  # Session.add is sync in SQLAlchemy — avoid an unawaited-coroutine warning
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = scalars_list or []
    db.execute = AsyncMock(return_value=result)
    return db


def _scenario(**overrides) -> EvaluationScenario:
    base = dict(
        id=uuid4(),
        code="S1",
        title="Cari jadwal SPMB",
        instruction="Tanyakan jadwal pendaftaran SPMB kepada asisten.",
        expected_task="jadwal",
        order_index=1,
        is_active=True,
        created_at=None,
    )
    base.update(overrides)
    return EvaluationScenario(**base)


@pytest.mark.asyncio
class TestScenarioCreate:
    async def test_duplicate_code_raises_409(self):
        db = _db_returning(scalar=_scenario())
        payload = admin_routes.ScenarioCreate(
            code="S1", title="t", instruction="i"
        )
        with pytest.raises(HTTPException) as exc_info:
            await admin_routes.create_scenario(payload, db=db)
        assert exc_info.value.status_code == 409
        db.add.assert_not_called()

    async def test_new_code_creates_and_commits(self):
        db = _db_returning(scalar=None)
        payload = admin_routes.ScenarioCreate(
            code="S9", title="Skenario baru", instruction="Lakukan X", order_index=3
        )
        result = await admin_routes.create_scenario(payload, db=db)
        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["code"] == "S9"
        assert result["order_index"] == 3
        assert result["is_active"] is True


@pytest.mark.asyncio
class TestScenarioUpdate:
    async def test_unknown_id_raises_404(self):
        db = _db_returning(scalar=None)
        with pytest.raises(HTTPException) as exc_info:
            await admin_routes.update_scenario(
                uuid4(), admin_routes.ScenarioUpdate(title="x"), db=db
            )
        assert exc_info.value.status_code == 404

    async def test_partial_update_only_touches_provided_fields(self):
        scenario = _scenario(title="Lama", is_active=True)
        db = _db_returning(scalar=scenario)
        result = await admin_routes.update_scenario(
            scenario.id, admin_routes.ScenarioUpdate(is_active=False), db=db
        )
        assert scenario.is_active is False
        assert scenario.title == "Lama"  # untouched
        assert result["is_active"] is False
        db.commit.assert_awaited_once()


@pytest.mark.asyncio
class TestScenarioList:
    async def test_returns_inactive_scenarios_too(self):
        rows = [_scenario(code="S1"), _scenario(id=uuid4(), code="S2", is_active=False)]
        db = _db_returning(scalars_list=rows)
        result = await admin_routes.list_scenarios_admin(db=db)
        assert [s["code"] for s in result["scenarios"]] == ["S1", "S2"]
        assert result["scenarios"][1]["is_active"] is False


def _request(headers: dict | None = None, client_host: str = "10.0.0.1"):
    request = MagicMock()
    request.headers = {k.lower(): v for k, v in (headers or {}).items()}
    request.client.host = client_host
    return request


@pytest.mark.asyncio
class TestPublicEvaluationRateLimit:
    async def test_over_limit_raises_429(self):
        limiter = AsyncMock()
        limiter.check_ip_limit = AsyncMock(return_value=False)
        with patch(
            "app.api.routes_evaluation_public.get_rate_limiter",
            AsyncMock(return_value=limiter),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await enforce_ip_rate_limit(_request())
        assert exc_info.value.status_code == 429

    async def test_within_limit_passes(self):
        limiter = AsyncMock()
        limiter.check_ip_limit = AsyncMock(return_value=True)
        with patch(
            "app.api.routes_evaluation_public.get_rate_limiter",
            AsyncMock(return_value=limiter),
        ):
            await enforce_ip_rate_limit(_request())  # no exception

    async def test_limiter_error_fails_open(self):
        with patch(
            "app.api.routes_evaluation_public.get_rate_limiter",
            AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            await enforce_ip_rate_limit(_request())  # no exception

    async def test_uses_first_hop_of_x_forwarded_for(self):
        limiter = AsyncMock()
        limiter.check_ip_limit = AsyncMock(return_value=True)
        with patch(
            "app.api.routes_evaluation_public.get_rate_limiter",
            AsyncMock(return_value=limiter),
        ):
            await enforce_ip_rate_limit(
                _request(headers={"x-forwarded-for": "203.0.113.7, 172.18.0.2"})
            )
        limiter.check_ip_limit.assert_awaited_once_with("203.0.113.7")
