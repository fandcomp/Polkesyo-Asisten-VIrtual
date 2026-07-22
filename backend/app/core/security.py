"""HTTP Basic Auth for /admin/* routes and agent-run introspection (CLAUDE.md §26.2/§30)."""
import logging
import secrets
from dataclasses import dataclass

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import settings
from app.services.rate_limiter_service import get_rate_limiter

logger = logging.getLogger(__name__)

_basic_auth = HTTPBasic()

# Reviewer-role second admin account (env-var based, same mechanism as the primary account —
# see CLAUDE.md-adjacent design note in IMPLEMENTATION.md's 2026-07-21 entry). `None` on
# `evaluation_tabs` means unrestricted; the second admin gets exactly these 4 of the Evaluation
# section's 12 sub-tabs. Full Document Review / Monitoring / Knowledge Graph access is granted
# implicitly — those routers all still gate on plain `require_admin_auth`, unchanged.
EVALUATION_TABS_SECOND_ADMIN = frozenset({"overview", "technical_logs", "acif_traces", "retrieval"})


@dataclass(frozen=True)
class AdminIdentity:
    username: str
    evaluation_tabs: frozenset[str] | None  # None = unrestricted (primary admin)


def _client_ip(request: Request) -> str:
    """Same X-Forwarded-For-first-hop convention as `routes_evaluation_public.py`'s
    `enforce_ip_rate_limit` — Caddy sets it in production, `request.client.host` is the
    direct-access dev fallback."""
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_bcrypt(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


async def get_current_admin(
    request: Request, credentials: HTTPBasicCredentials = Depends(_basic_auth)
) -> AdminIdentity:
    """Verify admin Basic Auth credentials against the primary account, then (if configured)
    the second reviewer-role account. Raises 401 on bad credentials, 429 if an IP has too many
    recent failed attempts (brute-force resistance — bcrypt's own cost factor slows a single
    guess but does nothing to cap total attempts over time), 503 if the server has no admin
    account configured at all.

    The rate limit counts FAILED attempts only, checked but not incremented up front (a cheap
    peek, before spending bcrypt's CPU cost) and incremented only in the failure branch at the
    bottom. It must never fire on a successful, correctly-authenticated request — every browser
    request the frontend makes to any /admin or /api/admin endpoint carries the same stored
    Basic-Auth header (see apiClient.ts), so a single admin dashboard page load can trigger many
    authenticated requests in a few seconds; counting successes here would lock out normal usage
    almost immediately (this happened once, 2026-07-21 — see IMPLEMENTATION.md).

    Usernames are compared with secrets.compare_digest to avoid timing side-channels; passwords
    are verified against bcrypt hashes (never stored/compared in plaintext). Both accounts'
    bcrypt checks run regardless of which username matched, so response timing doesn't reveal
    which of the two configured usernames (if either) was typed.
    """
    if not settings.admin_password_hash:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin authentication is not configured on this server.",
        )

    client_ip = _client_ip(request)
    limiter = None
    try:
        limiter = await get_rate_limiter()
        blocked = await limiter.is_admin_login_blocked(client_ip)
    except Exception as e:  # fail-open: limiter infra errors must not lock admins out
        logger.warning(f"Admin login rate limiter unavailable: {e}")
        blocked = False
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Terlalu banyak percobaan login admin. Silakan coba lagi nanti.",
        )

    primary_username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    primary_password_ok = _check_bcrypt(credentials.password, settings.admin_password_hash)

    second_username_ok = bool(settings.second_admin_username) and secrets.compare_digest(
        credentials.username, settings.second_admin_username
    )
    second_password_ok = _check_bcrypt(credentials.password, settings.second_admin_password_hash)

    if primary_username_ok and primary_password_ok:
        return AdminIdentity(username=credentials.username, evaluation_tabs=None)

    if second_username_ok and second_password_ok:
        return AdminIdentity(username=credentials.username, evaluation_tabs=EVALUATION_TABS_SECOND_ADMIN)

    try:
        if limiter is None:
            limiter = await get_rate_limiter()
        await limiter.record_admin_login_failure(client_ip)
    except Exception as e:  # fail-open: limiter infra errors must not block the 401 response
        logger.warning(f"Admin login failure recording unavailable: {e}")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid admin credentials.",
        headers={"WWW-Authenticate": "Basic"},
    )


async def require_admin_auth(admin: AdminIdentity = Depends(get_current_admin)) -> str:
    """Any valid admin identity — unchanged contract used by every router that doesn't need
    finer-grained section checks (Document Review, Monitoring, Knowledge Graph, agent-run
    introspection). Both the primary and second admin pass this."""
    return admin.username


def require_evaluation_tab(tab: str):
    """Dependency factory gating a specific Evaluation sub-tab's routes. `get_current_admin` is
    depended on here and (separately) by `require_admin_auth` at router-include time — FastAPI
    caches the dependency result per request, so this doesn't re-run the rate-limit/bcrypt work."""

    async def _check(admin: AdminIdentity = Depends(get_current_admin)) -> AdminIdentity:
        if admin.evaluation_tabs is not None and tab not in admin.evaluation_tabs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin tidak memiliki akses ke bagian evaluasi ini.",
            )
        return admin

    return _check
