"""OpenRouter LLM service — handle production LLM calls via OpenRouter API."""
import asyncio
import os
import logging
from dataclasses import dataclass
from datetime import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import OpenRouterUsageLog
from app.core.config import settings


logger = logging.getLogger(__name__)

# Caps concurrent in-flight OpenRouter requests per worker process at LLM_MAX_CONCURRENCY
# (CLAUDE.md §9.5/§25). This setting existed in config.py but was never enforced anywhere —
# the project's own request-queue module (request_queue_service.py, a Redis-backed queue from
# an early build phase) was written but never wired into chat_core.py or any route, so under
# real concurrent load nothing bounded how many simultaneous LLM calls this process would fire.
# A plain semaphore is the right fix for a *per-process* resource cap — a distributed Redis
# queue is architecturally heavier than this problem needs (it would only matter for
# coordinating the cap *across* multiple backend replicas, which this project doesn't do today;
# Redis-backed admission control can be revisited if/when it does). Module-level so it's shared
# by every caller of generate()/generate_with_fallback() in this process, including retries and
# the fallback-model path (generate_with_fallback calls generate() internally, so wrapping the
# semaphore inside generate() covers both without duplicating it at every call site).
_llm_semaphore = asyncio.Semaphore(settings.llm_max_concurrency)


class OpenRouterError(Exception):
    """OpenRouter service error."""
    pass


@dataclass
class GenerationResult:
    """Answer text plus the usage metadata Evaluation Layer Phase 1 needs
    (chat_evaluation_logs.model_used/input_tokens/output_tokens/estimated_cost) — previously
    generate()/generate_with_fallback() returned only the bare answer string, logging usage
    internally to OpenRouterUsageLog but never surfacing it to the caller."""
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float


class OpenRouterClient:
    """Production LLM client via OpenRouter (OpenAI-compatible API)."""

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    @staticmethod
    async def generate(
        prompt: str,
        db: AsyncSession | None = None,
        max_tokens: int = 600,
        temperature: float = 0.15,
        timeout: int = 30,
        model: str | None = None,
    ) -> GenerationResult:
        """Generate response using OpenRouter LLM.

        Args:
            prompt: Complete bounded prompt from Gate 4
            db: Database session for logging (optional)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0.0 = deterministic)
            timeout: Request timeout in seconds
            model: Override model id (defaults to the configured primary model)

        Returns:
            GenerationResult(text, model, prompt_tokens, completion_tokens, cost_usd)

        Raises:
            OpenRouterError: On API failure or invalid response
        """

        api_key = os.environ.get("OPENROUTER_API_KEY") or settings.openrouter_api_key
        if not api_key:
            logger.error("OPENROUTER_API_KEY not set")
            raise OpenRouterError("LLM service not configured")

        model = model or settings.openrouter_primary_model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://poltekkesjogja.ac.id",
            "X-Title": "Campus Virtual Assistant",
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": 0.95,
            # Reasoning-capable models (e.g. gemini-2.5-pro) otherwise spend part of
            # max_tokens on hidden "thinking" tokens, truncating the visible answer before
            # it finishes. We want the direct grounded answer, not exposed chain-of-thought.
            "reasoning": {"effort": "low", "exclude": True},
        }

        try:
            async with _llm_semaphore:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(
                        OpenRouterClient.API_URL,
                        json=payload,
                        headers=headers,
                    )

                    if response.status_code != 200:
                        error_msg = f"OpenRouter API error {response.status_code}"
                        logger.error(f"{error_msg}: {response.text}")
                        raise OpenRouterError(error_msg)

                    data = response.json()

                    # Extract answer
                    if "choices" not in data or len(data["choices"]) == 0:
                        raise OpenRouterError("No choices in API response")

                    answer = data["choices"][0].get("message", {}).get("content", "")
                    if not answer:
                        raise OpenRouterError("Empty response content")

                    usage = data.get("usage", {}) or {}
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_cost = usage.get("total_cost", 0)

                    # Log usage if database provided
                    if db:
                        await OpenRouterClient._log_usage(
                            db,
                            model=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            total_cost=total_cost,
                        )

                    logger.info(
                        f"OpenRouter LLM call successful. "
                        f"Model: {model}, "
                        f"Tokens: {usage.get('total_tokens', 0)}"
                    )

                    return GenerationResult(
                        text=answer,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=total_cost,
                    )

        except httpx.TimeoutException:
            logger.error("OpenRouter API timeout")
            raise OpenRouterError("LLM service timeout — please try again")
        except httpx.RequestError as e:
            logger.error(f"OpenRouter API request error: {e}")
            raise OpenRouterError("LLM service unavailable")
        except Exception as e:
            logger.error(f"Unexpected OpenRouter error: {e}")
            raise OpenRouterError(f"LLM service error: {str(e)}")

    @staticmethod
    async def generate_with_fallback(
        prompt: str,
        db: AsyncSession | None = None,
        max_tokens: int = 600,
        temperature: float = 0.15,
    ) -> GenerationResult:
        """Generate with automatic fallback to cheaper model on primary failure."""

        try:
            return await OpenRouterClient.generate(
                prompt,
                db=db,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except OpenRouterError as e:
            logger.warning(f"Primary model failed, trying fallback: {e}")

            result = await OpenRouterClient.generate(
                prompt,
                db=db,
                max_tokens=max_tokens,
                temperature=temperature,
                model=settings.openrouter_fallback_model,
            )
            logger.info("Fallback model succeeded")
            return result

    @staticmethod
    async def _log_usage(
        db: AsyncSession,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_cost: float,
    ) -> None:
        """Log OpenRouter API usage for cost tracking."""

        log_entry = OpenRouterUsageLog(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=total_cost,
            created_at=datetime.utcnow(),
        )

        db.add(log_entry)
        await db.commit()

        logger.debug(
            f"OpenRouter usage logged: {prompt_tokens} prompt + "
            f"{completion_tokens} completion tokens, ${total_cost:.6f}"
        )


async def check_openrouter_budget(db: AsyncSession) -> bool:
    """Check if OpenRouter daily budget has been exceeded."""

    from sqlalchemy import select, func
    from datetime import datetime, timedelta

    today = datetime.utcnow().date()
    tomorrow = today + timedelta(days=1)

    stmt = (
        select(func.sum(OpenRouterUsageLog.cost_usd))
        .where(
            OpenRouterUsageLog.created_at >= datetime.combine(today, datetime.min.time()),
            OpenRouterUsageLog.created_at < datetime.combine(tomorrow, datetime.min.time()),
        )
    )

    try:
        result = await db.execute(stmt)
        total_cost = result.scalar() or 0.0
    except Exception as e:
        # Fail open: a broken budget query must not poison the request's DB
        # session (aborted transaction) or block the assistant.
        await db.rollback()
        logger.error(f"Budget query failed, allowing request: {e}")
        return True

    budget = float(os.environ.get("OPENROUTER_DAILY_BUDGET_USD", "10"))

    if total_cost >= budget:
        logger.warning(
            f"Daily OpenRouter budget exceeded: ${total_cost:.2f} >= ${budget:.2f}"
        )
        return False

    return True
