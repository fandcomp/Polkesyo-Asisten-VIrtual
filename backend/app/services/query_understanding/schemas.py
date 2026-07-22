"""Schemas for the Query Understanding Layer."""
from pydantic import BaseModel, Field


class QueryAnalysis(BaseModel):
    """Structured result of analyzing one user question before retrieval.

    ``original_question`` is untouched user input (what ACIF Gate 1 already checked).
    ``normalized_question`` is the retrieval-oriented normalization of that input.
    ``resolved_question`` equals ``normalized_question`` unless conversation-context
    resolution appended an active topic (elliptical follow-ups like "syaratnya apa?").
    """

    original_question: str
    normalized_question: str
    resolved_question: str
    detected_terms: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    # acronym token -> expansion phrases (per-word matching support for ACIF Gate 2)
    term_expansions: dict[str, list[str]] = Field(default_factory=dict)
    intent: str = "unknown"
    intent_confidence: float = 0.3
    rewritten_queries: list[str] = Field(default_factory=list)
    is_short_query: bool = False
    exact_term_matched: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None
    context_used: bool = False
    language: str = "id"
    topic: str | None = None
    notes: str = ""
