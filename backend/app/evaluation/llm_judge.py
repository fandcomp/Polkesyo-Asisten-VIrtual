"""RAGAS-style LLM-as-judge scoring — Evaluation Layer Phase 5.

Scores one (question, context, answer) triple for faithfulness, answer relevance, and
hallucination, populating the previously-empty EvaluationResult.faithfulness_score /
.answer_relevance_score / .hallucination_detected columns. Gated by
settings.evaluation_llm_judge_enabled and only ever invoked from run_evaluation.py's gold-QA
runner (evaluation_mode) — never on production /chat traffic, never a production LLM cost.
"""
import json
import logging
import re
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.openrouter_client import OpenRouterClient, OpenRouterError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JudgeResult:
    faithfulness_score: float | None
    answer_relevance_score: float | None
    hallucination_detected: bool | None


_JUDGE_PROMPT = """You are an evaluation judge for a campus virtual assistant. Score the ANSWER \
strictly against the CONTEXT below — do not use outside knowledge, and do not reward an answer \
for being fluent or plausible if it is not grounded in the CONTEXT.

QUESTION:
{question}

CONTEXT (the only allowed factual source):
{context}

ANSWER:
{answer}

Return ONLY a JSON object (no markdown fence, no commentary) with exactly these fields:
{{
  "faithfulness_score": <float 0.0-1.0, fraction of the answer's claims directly supported by the context>,
  "answer_relevance_score": <float 0.0-1.0, how directly the answer addresses the question asked>,
  "hallucination_detected": <true if the answer states any fact not present in the context, else false>
}}
"""


async def judge_answer(
    question: str,
    context: str,
    answer: str,
    db: AsyncSession | None = None,
) -> JudgeResult | None:
    """Score one (question, context, answer) triple.

    Returns None — never a failing 0.0/False — when the judge is disabled, there is no context
    to score against, or the LLM call/parse fails. Callers must treat None as "not scored" (same
    convention as metrics.precision_at_k's docstring), not as a negative result.
    """
    if not settings.evaluation_llm_judge_enabled:
        return None
    if not context.strip() or not answer.strip():
        return None

    prompt = _JUDGE_PROMPT.format(
        question=question.strip(),
        context=context[:6000],
        answer=answer[:3000],
    )

    try:
        result = await OpenRouterClient.generate(
            prompt,
            db=db,
            model=settings.openrouter_verification_model,
            max_tokens=300,
            temperature=0.0,
            timeout=20,
        )
    except OpenRouterError as e:
        logger.warning(f"LLM judge call failed: {e}")
        return None

    try:
        return _parse_judge_response(result.text)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"LLM judge response could not be parsed: {e}")
        return None


def _parse_judge_response(raw: str) -> JudgeResult:
    """Parse the judge's JSON object, tolerating a markdown code fence (same convention as
    OutputClaimVerifier._parse_llm_verification)."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got: {type(data)}")

    faithfulness = data.get("faithfulness_score")
    relevance = data.get("answer_relevance_score")
    hallucination = data.get("hallucination_detected")

    return JudgeResult(
        faithfulness_score=float(faithfulness) if faithfulness is not None else None,
        answer_relevance_score=float(relevance) if relevance is not None else None,
        hallucination_detected=bool(hallucination) if hallucination is not None else None,
    )
