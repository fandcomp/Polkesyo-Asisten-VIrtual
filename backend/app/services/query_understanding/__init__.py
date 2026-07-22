"""Query Understanding Layer — normalization, acronym expansion, query rewriting.

Runs AFTER ACIF Gate 1 (which always checks the ORIGINAL user input) and BEFORE retrieval.
It improves how the assistant searches official sources; it never generates answers and it
never weakens ACIF filtering.
"""
from app.services.query_understanding.query_understanding_service import QueryUnderstandingService
from app.services.query_understanding.schemas import QueryAnalysis

__all__ = ["QueryUnderstandingService", "QueryAnalysis"]
