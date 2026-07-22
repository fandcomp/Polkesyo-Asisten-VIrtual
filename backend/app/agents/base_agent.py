"""Base agent contract for the Agentic Orchestration Architecture (CLAUDE.md §11A).

Every agent has a name, an async run step, an execution status, and a persisted log entry
(agent_run_logs) — "Jangan membuat agent bekerja tanpa log" (CLAUDE.md §11A.5).
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRunLog

logger = logging.getLogger(__name__)

_MAX_SUMMARY_CHARS = 500


@dataclass
class AgentResult:
    """Uniform result envelope every agent returns from execute()."""

    status: str  # "success" | "error"
    output: Any = None
    error: str | None = None
    latency_ms: float = 0.0


class BaseAgent:
    """Abstract agent: subclasses implement `_run`, `execute` handles timing + logging."""

    name: str = "BaseAgent"

    async def execute(
        self,
        input_data: dict,
        db: AsyncSession | None = None,
        task_type: str | None = None,
    ) -> AgentResult:
        """Run the agent, time it, and persist one agent_run_logs row if `db` is given."""
        start = time.perf_counter()
        try:
            output = await self._run(input_data)
            result = AgentResult(
                status="success",
                output=output,
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 - an agent failure must not crash the orchestrator
            logger.error(f"[{self.name}] run failed: {exc}")
            result = AgentResult(
                status="error",
                error=str(exc),
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        if db is not None:
            await self._log_run(db, input_data, result, task_type)

        return result

    async def _run(self, input_data: dict) -> Any:
        raise NotImplementedError

    async def _log_run(
        self,
        db: AsyncSession,
        input_data: dict,
        result: AgentResult,
        task_type: str | None,
    ) -> None:
        try:
            entry = AgentRunLog(
                agent_name=self.name,
                task_type=task_type,
                input_summary=self._summarize(input_data),
                output_summary=self._summarize(result.output),
                status=result.status,
                latency_ms=result.latency_ms,
                error_message=result.error,
            )
            db.add(entry)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 - logging must never break the pipeline
            logger.error(f"[{self.name}] failed to persist agent_run_logs: {exc}")

    @staticmethod
    def _summarize(data: Any) -> str | None:
        """Truncated summary for agent_run_logs — full payloads are too large to store per row."""
        if data is None:
            return None
        try:
            text = json.dumps(data, default=str, ensure_ascii=False)
        except Exception:
            text = str(data)
        if len(text) > _MAX_SUMMARY_CHARS:
            text = text[:_MAX_SUMMARY_CHARS] + "...(truncated)"
        return text
