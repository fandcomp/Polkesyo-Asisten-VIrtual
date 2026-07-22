"""Session-error mapping in the chat routes.

Only SessionNotFoundError may produce the 404 "Sesi Anda tidak ditemukan" response.
Regression tests for the 2026-07-10 incident: the routes caught bare ValueError, so
infrastructure failures deep in the pipeline (fd exhaustion) were mislabeled as an
expired session, telling users to reload for a problem a reload cannot fix.
"""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import routes_chat, routes_chat_agentic
from app.core.errors import SessionNotFoundError
from app.schemas.chat import ChatRequest

_SESSION_MESSAGE = "Sesi Anda tidak ditemukan atau sudah berakhir."


def _request() -> ChatRequest:
    return ChatRequest(message="kapan spmb mandiri dibuka")


def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
class TestChatRoute:
    async def test_missing_cookie_returns_400(self):
        response = await routes_chat.chat(_request(), chat_session_id=None, db=AsyncMock())
        assert response.status_code == 400
        assert _body(response)["error_type"] == "session_not_found"

    async def test_session_not_found_error_returns_404(self, monkeypatch):
        monkeypatch.setattr(
            routes_chat.ChatCoreService,
            "process_message",
            AsyncMock(side_effect=SessionNotFoundError("Session not found")),
        )
        response = await routes_chat.chat(_request(), chat_session_id=uuid4(), db=AsyncMock())
        assert response.status_code == 404
        body = _body(response)
        assert body["error_type"] == "session_not_found"
        assert _SESSION_MESSAGE in body["message"]

    async def test_other_value_errors_are_not_mislabeled_as_session_errors(self, monkeypatch):
        monkeypatch.setattr(
            routes_chat.ChatCoreService,
            "process_message",
            AsyncMock(side_effect=ValueError("Too many open files")),
        )
        # Must propagate (handled by the app-level 500 handler), never the session 404.
        with pytest.raises(ValueError):
            await routes_chat.chat(_request(), chat_session_id=uuid4(), db=AsyncMock())


@pytest.mark.asyncio
class TestAgenticChatRoute:
    async def test_missing_cookie_returns_400(self):
        response = await routes_chat_agentic.chat_agentic(
            _request(), chat_session_id=None, db=AsyncMock()
        )
        assert response.status_code == 400
        assert _body(response)["error_type"] == "session_not_found"

    async def test_session_not_found_error_returns_404(self, monkeypatch):
        monkeypatch.setattr(
            routes_chat_agentic.OrchestratorAgent,
            "handle_chat_request",
            AsyncMock(side_effect=SessionNotFoundError("Session not found")),
        )
        response = await routes_chat_agentic.chat_agentic(
            _request(), chat_session_id=uuid4(), db=AsyncMock()
        )
        assert response.status_code == 404
        body = _body(response)
        assert body["error_type"] == "session_not_found"
        assert _SESSION_MESSAGE in body["message"]

    async def test_other_value_errors_are_not_mislabeled_as_session_errors(self, monkeypatch):
        monkeypatch.setattr(
            routes_chat_agentic.OrchestratorAgent,
            "handle_chat_request",
            AsyncMock(side_effect=ValueError("Too many open files")),
        )
        with pytest.raises(ValueError):
            await routes_chat_agentic.chat_agentic(
                _request(), chat_session_id=uuid4(), db=AsyncMock()
            )
