"""Resolve elliptical follow-up questions from limited conversation context.

Consent-aware by contract: callers must pass ``history_allowed=True`` only when the
session's latest consent is ``history_and_analytics``. Without history, an elliptical
question yields a clarification request instead of a wrong guess or a hard fallback.
"""
from dataclasses import dataclass

from app.services.query_understanding.domain_terms_loader import DomainTerms
from app.services.query_understanding.normalizer import QueryNormalizer

_QUESTION_WORDS = {"kapan", "berapa", "apa", "siapa", "dimana", "mana", "bagaimana", "gimana", "kok"}

# Words that carry a concrete campus topic on their own — if present, the question is
# self-contained and needs no history resolution.
_MAX_ELLIPTICAL_TOKENS = 5

GENERIC_CLARIFICATION = (
    "Pertanyaan tersebut masih terlalu umum. Apakah yang dimaksud terkait pendaftaran SPMB, "
    "pendaftaran ulang, atau layanan akademik?"
)

_INTENT_CLARIFICATIONS: dict[str, str] = {
    "requirement": (
        "Syarat untuk layanan apa yang dimaksud, misalnya SPMB, pendaftaran ulang, "
        "atau layanan akademik?"
    ),
    "document_requirement": (
        "Berkas untuk keperluan apa yang dimaksud, misalnya pendaftaran SPMB, "
        "pendaftaran ulang, atau layanan akademik?"
    ),
    "schedule": (
        "Yang dimaksud jadwal pendaftaran SPMB, pendaftaran ulang, atau layanan akademik? "
        "Saya bisa mencarikan jadwalnya setelah jenisnya jelas."
    ),
    "fee": "Biaya untuk layanan apa yang dimaksud, misalnya SPMB atau uang kuliah (UKT)?",
}


@dataclass(frozen=True)
class ResolutionResult:
    resolved_question: str
    context_used: bool = False
    needs_clarification: bool = False
    clarification_question: str | None = None


class ConversationContextResolver:
    def __init__(self, terms: DomainTerms):
        self._terms = terms

    def resolve(
        self,
        normalized: str,
        history: list[dict] | None,
        history_allowed: bool,
        intent_hint: str | None = None,
    ) -> ResolutionResult:
        if not self._is_elliptical(normalized):
            return ResolutionResult(resolved_question=normalized)

        if history_allowed and history:
            topic_terms = self._find_topic_terms(history)
            if topic_terms:
                resolved = f"{normalized} {' '.join(topic_terms)}"
                return ResolutionResult(resolved_question=resolved, context_used=True)

        clarification = _INTENT_CLARIFICATIONS.get(intent_hint or "", GENERIC_CLARIFICATION)
        return ResolutionResult(
            resolved_question=normalized,
            needs_clarification=True,
            clarification_question=clarification,
        )

    def _is_elliptical(self, normalized: str) -> bool:
        """Short question that references an implicit topic ("syaratnya apa?")."""
        tokens = normalized.split()
        if not tokens or len(tokens) > _MAX_ELLIPTICAL_TOKENS:
            return False
        # Self-contained if it already names an acronym or a domain topic keyword.
        if self._has_own_topic(tokens, normalized):
            return False
        has_nya_suffix = any(t.endswith("nya") and len(t) > 3 for t in tokens)
        has_question_word = any(t in _QUESTION_WORDS for t in tokens)
        return has_nya_suffix or has_question_word

    def _has_own_topic(self, tokens: list[str], normalized: str) -> bool:
        if any(t in self._terms.acronyms for t in tokens):
            return True
        # Topic-bearing concrete nouns (not the generic aliases like "kapan"/"berapa").
        # "daftar"/"daftarnya" carry the registration topic themselves, unlike attribute
        # words ("syaratnya", "berkasnya") that need an antecedent topic.
        # Contact/form questions are campus-wide targets — self-contained without an
        # antecedent ("kontak adminnya mana", "formnya ada?").
        topic_nouns = {"pendaftaran", "daftar", "daftarnya", "mendaftar", "registrasi",
                       "spmb", "ukt", "krs", "khs", "wisuda", "kuliah",
                       "beasiswa", "seleksi", "prodi", "jurusan", "poltekkes",
                       "kontak", "admin", "adminnya", "form", "formulir", "formnya"}
        return any(t in topic_nouns for t in tokens) or "poltekkes" in normalized

    def _find_topic_terms(self, history: list[dict]) -> list[str]:
        """Scan the last 3 user turns (newest first) for an acronym or concrete topic."""
        user_turns = [h for h in history if h.get("role") == "user"]
        for turn in reversed(user_turns[-3:]):
            turn_norm = QueryNormalizer.normalize(turn.get("message", ""))
            turn_tokens = turn_norm.split()
            for token in turn_tokens:
                entry = self._terms.acronyms.get(token)
                if entry:
                    return [token, entry.expansion]
            for noun in ("pendaftaran", "seleksi", "wisuda", "beasiswa", "kuliah"):
                if noun in turn_tokens:
                    return [noun]
        return []
