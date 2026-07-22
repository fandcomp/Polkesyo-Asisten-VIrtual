"""Retrieval-oriented question normalization.

Builds on ACIF's TextNormalizer (zero-width strip, unicode NFKD, lowercase) and then
removes punctuation for token matching. The result is used ONLY for retrieval and
term matching — ACIF Gate 1 always operates on the original user input.
"""
import re

from app.services.acif.text_normalizer import TextNormalizer


class QueryNormalizer:
    @staticmethod
    def normalize(text: str) -> str:
        normalized = TextNormalizer.normalize(text or "")
        # Punctuation to spaces so "spmb?" tokenizes as "spmb"; keep digits/letters intact.
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def tokens(text: str) -> list[str]:
        return QueryNormalizer.normalize(text).split()
