"""Rate limiter service using Redis for high-traffic protection."""
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

try:
    import redis.asyncio as aioredis
except ImportError:
    import aioredis

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


class RateLimiterService:
    """Rate limiting using Redis sliding window."""

    # Default limits
    LIMIT_SESSION_PER_MINUTE = 10      # 10 requests per session per minute
    LIMIT_IP_PER_MINUTE = 60           # 60 requests per IP per minute
    LIMIT_SESSION_PER_DAY = 50         # 50 LLM calls per session per day
    LIMIT_GLOBAL_PER_HOUR = 1000       # 1000 total requests per hour
    LIMIT_ADMIN_LOGIN_PER_WINDOW = 5   # 5 admin auth attempts per IP per window
    ADMIN_LOGIN_WINDOW_SECONDS = 900   # 15 minutes

    # Redis key prefixes
    PREFIX_SESSION_MINUTE = "ratelimit:session:minute:"
    PREFIX_IP_MINUTE = "ratelimit:ip:minute:"
    PREFIX_SESSION_DAY = "ratelimit:session:day:"
    PREFIX_GLOBAL_HOUR = "ratelimit:global:hour"
    PREFIX_ADMIN_LOGIN = "ratelimit:admin_login:"

    def __init__(self):
        """Initialize rate limiter."""
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
            logger.info("Rate limiter connected to Redis")
        except Exception as e:
            logger.error(f"Rate limiter connection failed: {e}")
            self.client = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self.client:
            await self.client.close()

    async def check_session_limit(self, session_id: str) -> bool:
        """Check if session is within per-minute limit."""
        if not self.client:
            return True  # Pass if Redis unavailable

        key = f"{self.PREFIX_SESSION_MINUTE}{session_id}"

        try:
            current = await self.client.incr(key)
            if current == 1:
                # First request, set expiration
                await self.client.expire(key, 60)
            elif current > self.LIMIT_SESSION_PER_MINUTE:
                logger.warning(
                    f"Session rate limit exceeded: {session_id} "
                    f"({current}/{self.LIMIT_SESSION_PER_MINUTE})"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Session rate check failed: {e}")
            return True

    async def check_ip_limit(self, ip_address: str) -> bool:
        """Check if IP is within per-minute limit."""
        if not self.client:
            return True

        key = f"{self.PREFIX_IP_MINUTE}{ip_address}"

        try:
            current = await self.client.incr(key)
            if current == 1:
                await self.client.expire(key, 60)
            elif current > self.LIMIT_IP_PER_MINUTE:
                logger.warning(
                    f"IP rate limit exceeded: {ip_address} "
                    f"({current}/{self.LIMIT_IP_PER_MINUTE})"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"IP rate check failed: {e}")
            return True

    async def check_session_daily_limit(self, session_id: str) -> bool:
        """Check if session is within daily LLM call limit."""
        if not self.client:
            return True

        key = f"{self.PREFIX_SESSION_DAY}{session_id}"
        today = datetime.utcnow().date()
        date_key = f"{key}:{today}"

        try:
            current = await self.client.incr(date_key)
            if current == 1:
                # Set expiration to end of today
                tomorrow = today + timedelta(days=1)
                ttl = int((datetime.combine(tomorrow, datetime.min.time()) - datetime.utcnow()).total_seconds())
                await self.client.expire(date_key, max(ttl, 1))
            elif current > self.LIMIT_SESSION_PER_DAY:
                logger.warning(
                    f"Session daily limit exceeded: {session_id} "
                    f"({current}/{self.LIMIT_SESSION_PER_DAY})"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Session daily rate check failed: {e}")
            return True

    async def check_global_limit(self) -> bool:
        """Check global hourly limit."""
        if not self.client:
            return True

        key = self.PREFIX_GLOBAL_HOUR

        try:
            current = await self.client.incr(key)
            if current == 1:
                await self.client.expire(key, 3600)
            elif current > self.LIMIT_GLOBAL_PER_HOUR:
                logger.warning(
                    f"Global rate limit exceeded "
                    f"({current}/{self.LIMIT_GLOBAL_PER_HOUR})"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Global rate check failed: {e}")
            return True

    async def is_admin_login_blocked(self, ip_address: str) -> bool:
        """Peek at an IP's failed-admin-login count WITHOUT incrementing it.

        Separate from `check_ip_limit` (chat traffic volume, 60/min) — this is brute-force
        lockout semantics, meant to count only failed credential attempts, not every
        successfully-authenticated admin request. (An earlier version incremented on every
        request regardless of outcome, which locked out real admins after a handful of normal
        dashboard page loads — each firing several parallel authenticated API calls. Fixed
        2026-07-21: only `record_admin_login_failure` below increments the counter, and only on
        an actual bad-credential outcome.) Fails open on Redis unavailability, matching every
        other method here — a rate limiter outage must not lock admins out entirely.
        """
        if not self.client:
            return False

        key = f"{self.PREFIX_ADMIN_LOGIN}{ip_address}"
        try:
            current = await self.client.get(key)
            current_int = int(current) if current else 0
            return current_int >= self.LIMIT_ADMIN_LOGIN_PER_WINDOW
        except Exception as e:
            logger.warning(f"Admin login block-check failed: {e}")
            return False

    async def record_admin_login_failure(self, ip_address: str) -> None:
        """Increment an IP's failed-admin-login count. Call only when credentials were actually
        wrong — never on a successful auth, and never as a side effect of merely checking
        whether the IP is currently blocked (see `is_admin_login_blocked`)."""
        if not self.client:
            return

        key = f"{self.PREFIX_ADMIN_LOGIN}{ip_address}"
        try:
            current = await self.client.incr(key)
            if current == 1:
                await self.client.expire(key, self.ADMIN_LOGIN_WINDOW_SECONDS)
        except Exception as e:
            logger.warning(f"Admin login failure recording failed: {e}")

    async def get_session_remaining(self, session_id: str) -> int:
        """Get remaining requests for session."""
        if not self.client:
            return self.LIMIT_SESSION_PER_MINUTE

        key = f"{self.PREFIX_SESSION_MINUTE}{session_id}"

        try:
            current = await self.client.get(key)
            current_int = int(current) if current else 0
            return max(0, self.LIMIT_SESSION_PER_MINUTE - current_int)
        except Exception as e:
            logger.warning(f"Get remaining failed: {e}")
            return self.LIMIT_SESSION_PER_MINUTE


# Global instance
_rate_limiter: Optional[RateLimiterService] = None


async def get_rate_limiter() -> RateLimiterService:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiterService()
        await _rate_limiter.connect()
    return _rate_limiter


async def close_rate_limiter() -> None:
    """Close rate limiter."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.disconnect()
        _rate_limiter = None
