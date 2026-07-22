"""ACIF schemas and data structures."""
from enum import Enum
from pydantic import BaseModel


class ACIFDecision(str, Enum):
    """ACIF decision outcomes."""
    ACCEPT = "accept"
    CAUTION = "caution"
    REJECT = "reject"


class ACIFGate1Result(BaseModel):
    """Gate 1 result — input integrity assessment."""
    decision: ACIFDecision
    score: float  # 0.0 to 1.0
    risk_signals: list[str] = []
    reasoning: str = ""
    # Topical domain validation (CLAUDE.md §12) — orthogonal to the injection score above:
    # a clean-looking question can still be out of scope (e.g. stock-trading advice).
    domain_violation: bool = False
    domain_topics: list[str] = []
