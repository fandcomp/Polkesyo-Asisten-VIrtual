"""Participant-facing Evaluation Layer endpoints (Phase 4) — scenarios, ASQ, SUS.

Not admin-protected: these back the /evaluation participant flow, a dedicated route not linked
from the public site's normal navigation ("controlled evaluation route" per the spec) — a
participant filling out a study form has no reason to hold admin credentials. Normal chat
(`POST /chat` without evaluation_mode) never surfaces ASQ/SUS regardless of this router's
existence — that's enforced entirely on the frontend (ASQ/SUS forms only render inside the
/evaluation flow, never inside the public AssistantWidget).
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.db.models import AsqResponse, EvaluationScenario, SusResponse
from app.services.rate_limiter_service import get_rate_limiter

logger = logging.getLogger(__name__)


async def enforce_ip_rate_limit(request: Request) -> None:
    """Per-IP rate limit for these unauthenticated participant endpoints (CLAUDE.md §26.2).

    Uses the same Redis sliding window as the chat pipeline. The client IP comes from
    X-Forwarded-For's first hop (Caddy sets it in production) with request.client.host as
    the direct-access fallback. Fail-open on limiter errors, same policy as chat_core —
    a Redis outage must not take the participant study down with it.
    """
    forwarded_for = request.headers.get("x-forwarded-for", "")
    client_ip = forwarded_for.split(",")[0].strip() if forwarded_for else (
        request.client.host if request.client else "unknown"
    )
    try:
        limiter = await get_rate_limiter()
        allowed = await limiter.check_ip_limit(client_ip)
    except Exception as e:  # fail-open: limiter infra errors must not block participants
        logger.warning(f"Evaluation rate limiter unavailable: {e}")
        return
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Anda mengirim terlalu banyak permintaan. Silakan tunggu sebentar dan coba lagi.",
        )


router = APIRouter(
    prefix="/api/evaluation",
    tags=["evaluation"],
    dependencies=[Depends(enforce_ip_rate_limit)],
)


@router.get("/scenarios")
async def list_scenarios(db: AsyncSession = Depends(get_db)):
    """Active scenarios, in display order, for the /evaluation participant flow."""
    rows = (
        await db.execute(
            select(EvaluationScenario)
            .where(EvaluationScenario.is_active.is_(True))
            .order_by(EvaluationScenario.order_index)
        )
    ).scalars().all()

    return {
        "scenarios": [
            {
                "id": str(s.id),
                "code": s.code,
                "title": s.title,
                "instruction": s.instruction,
                "expected_task": s.expected_task,
                "order_index": s.order_index,
            }
            for s in rows
        ]
    }


class AsqSubmission(BaseModel):
    """After-Scenario Questionnaire submission — 3 items, 1-7 scale."""
    participant_code: str = Field(..., min_length=1, max_length=100)
    scenario_code: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = None
    trace_id: Optional[str] = None
    asq_1: int = Field(..., ge=1, le=7)
    asq_2: int = Field(..., ge=1, le=7)
    asq_3: int = Field(..., ge=1, le=7)
    notes: Optional[str] = None


@router.post("/asq")
async def submit_asq(submission: AsqSubmission, db: AsyncSession = Depends(get_db)):
    """Store an ASQ response. average_score = (asq_1 + asq_2 + asq_3) / 3."""
    if not settings.asq_enabled:
        raise HTTPException(status_code=403, detail="ASQ evaluation is disabled.")

    scenario = (
        await db.execute(select(EvaluationScenario).where(EvaluationScenario.code == submission.scenario_code))
    ).scalar_one_or_none()
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_code: {submission.scenario_code}")

    average_score = (submission.asq_1 + submission.asq_2 + submission.asq_3) / 3

    response = AsqResponse(
        participant_code=submission.participant_code,
        scenario_id=scenario.id,
        scenario_code=submission.scenario_code,
        session_id=submission.session_id,
        trace_id=submission.trace_id,
        asq_1=submission.asq_1,
        asq_2=submission.asq_2,
        asq_3=submission.asq_3,
        average_score=average_score,
        notes=submission.notes,
    )
    db.add(response)
    await db.commit()
    await db.refresh(response)

    return {"id": str(response.id), "average_score": average_score}


class SusSubmission(BaseModel):
    """System Usability Scale submission — 10 items, 1-5 scale."""
    participant_code: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = None
    sus_1: int = Field(..., ge=1, le=5)
    sus_2: int = Field(..., ge=1, le=5)
    sus_3: int = Field(..., ge=1, le=5)
    sus_4: int = Field(..., ge=1, le=5)
    sus_5: int = Field(..., ge=1, le=5)
    sus_6: int = Field(..., ge=1, le=5)
    sus_7: int = Field(..., ge=1, le=5)
    sus_8: int = Field(..., ge=1, le=5)
    sus_9: int = Field(..., ge=1, le=5)
    sus_10: int = Field(..., ge=1, le=5)
    notes: Optional[str] = None


def calculate_sus_score(scores: list[int]) -> float:
    """Standard SUS scoring: odd items contribute (score-1), even items contribute (5-score),
    sum * 2.5 gives a 0-100 scale score. `scores` is sus_1..sus_10 in order (1-indexed items,
    0-indexed list)."""
    total = 0
    for i, score in enumerate(scores):
        item_number = i + 1
        total += (score - 1) if item_number % 2 == 1 else (5 - score)
    return total * 2.5


@router.post("/sus")
async def submit_sus(submission: SusSubmission, db: AsyncSession = Depends(get_db)):
    """Store a SUS response — shown once after all scenarios are completed."""
    if not settings.sus_enabled:
        raise HTTPException(status_code=403, detail="SUS evaluation is disabled.")

    scores = [
        submission.sus_1, submission.sus_2, submission.sus_3, submission.sus_4, submission.sus_5,
        submission.sus_6, submission.sus_7, submission.sus_8, submission.sus_9, submission.sus_10,
    ]
    sus_score = calculate_sus_score(scores)

    response = SusResponse(
        participant_code=submission.participant_code,
        session_id=submission.session_id,
        sus_1=submission.sus_1,
        sus_2=submission.sus_2,
        sus_3=submission.sus_3,
        sus_4=submission.sus_4,
        sus_5=submission.sus_5,
        sus_6=submission.sus_6,
        sus_7=submission.sus_7,
        sus_8=submission.sus_8,
        sus_9=submission.sus_9,
        sus_10=submission.sus_10,
        sus_score=sus_score,
        notes=submission.notes,
    )
    db.add(response)
    await db.commit()
    await db.refresh(response)

    return {"id": str(response.id), "sus_score": sus_score}
