"""ACIF Gate 2: Context Integrity Scoring."""
import re

from app.core.config import settings
from app.services.acif.risk_signals import RiskSignals
from app.services.acif.schemas import ACIFDecision


class ContextIntegrityScorer:
    """Score retrieved chunks for integrity before LLM.

    Max achievable score without graph corroboration is 0.85 by design: the
    ``no_contradiction`` dimension (0.10) is awarded only when graph evidence exists for
    the query AND the chunk does not conflict with it — absence of graph evidence is not
    proof of non-contradiction, so the dimension stays unawarded in that case.
    """

    SCORING_DIMENSIONS = {
        "semantic_relevance": 0.25,
        "official_source": 0.20,
        "freshness": 0.15,
        "intent_match": 0.15,
        "no_injection": 0.15,
        "no_contradiction": 0.10,
    }

    @staticmethod
    async def score_context(
        chunk: dict,
        query: str,
        query_context: dict | None = None,
    ) -> dict:
        """Score a retrieved chunk on integrity dimensions.

        ``query_context`` (optional, from the Query Understanding Layer):
        - ``term_expansions``: acronym token -> expansion phrases — a query token also
          counts as matched when one of its expansions appears in the chunk ("spmb"
          matches a chunk that spells out "seleksi penerimaan mahasiswa baru").
        - ``exact_term_matched``: a detected domain acronym/term appeared verbatim.
        - ``graph_results_present`` + ``graph_entities``: enables the no_contradiction
          dimension (see class docstring).
        Existing callers without query_context get the exact pre-upgrade scoring.
        """
        query_context = query_context or {}
        score = 0.0

        # Semantic relevance (0-1 from metadata). Cosine distance > 1 produces a negative
        # similarity artifact — clamp to [0, 1]; a negative value carries no more evidence
        # of irrelevance than zero does, and must not eat into the other dimensions.
        raw_similarity = chunk.get("similarity_score", 0.5)
        similarity = max(0.0, min(1.0, raw_similarity))
        score += similarity * ContextIntegrityScorer.SCORING_DIMENSIONS["semantic_relevance"]

        # Official source check
        is_approved = chunk.get("metadata", {}).get("status") == "approved"
        if is_approved:
            score += ContextIntegrityScorer.SCORING_DIMENSIONS["official_source"]

        # Freshness (assume recent chunks are fresh)
        score += 0.1  # Simplified

        # Intent match (keyword overlap). \w+ tokenization so trailing punctuation in the
        # query ("spmb?") cannot zero out its most important term.
        content = chunk.get("content", "").lower()
        content_tokens = set(re.findall(r"\w+", content))
        query_words = re.findall(r"\w+", query.lower())
        term_expansions = query_context.get("term_expansions") or {}
        matched = 0
        for word in query_words:
            if word in content_tokens:
                matched += 1
            elif any(exp in content for exp in term_expansions.get(word, [])):
                matched += 1
        intent_score = matched / max(1, len(query_words))
        score += intent_score * ContextIntegrityScorer.SCORING_DIMENSIONS["intent_match"]

        # No injection in chunk
        if not ContextIntegrityScorer._has_injection(chunk.get("content", "")):
            score += ContextIntegrityScorer.SCORING_DIMENSIONS["no_injection"]

        # No contradiction — only assessable when graph evidence exists for this query.
        graph_awarded = False
        if query_context.get("graph_results_present"):
            graph_entities = [
                (e or "").lower() for e in query_context.get("graph_entities", []) if e
            ]
            if graph_entities and any(entity in content for entity in graph_entities):
                score += ContextIntegrityScorer.SCORING_DIMENSIONS["no_contradiction"]
                graph_awarded = True

        # Bounded recall aid for short acronym queries: an APPROVED chunk that verbatim
        # contains a detected domain term gets a small bonus. Thresholds are unchanged and
        # Gates 3/5 still apply — this cannot admit an unapproved or injected chunk.
        bonus_applied = False
        if query_context.get("exact_term_matched") and is_approved:
            detected = [t for t in query_context.get("detected_terms", []) if t]
            if any(t in content_tokens for t in detected):
                score += settings.acif_context_exact_term_bonus
                bonus_applied = True

        # Structural corroboration: the chunking pipeline now tags each chunk with the
        # section heading it falls under (e.g. "C. Mekanisme Pendaftaran"), populated for
        # the first time as of this change — previously always empty. A chunk whose own
        # heading shares vocabulary with the question is independent structural evidence
        # of relevance, on top of (not instead of) semantic/keyword matching — same bounded-
        # bonus pattern as exact_term_bonus above, so it can nudge ranking but never by
        # itself admit a chunk that failed the other integrity checks.
        section_match = False
        section_text = (chunk.get("metadata", {}) or {}).get("section") or ""
        if section_text and is_approved:
            section_tokens = set(re.findall(r"\w+", section_text.lower()))
            if section_tokens & set(query_words):
                score += settings.acif_context_section_match_bonus
                section_match = True

        # Min score = 0, Max = 1
        final_score = min(1.0, max(0.0, score))

        # Decision thresholds (from config; deployed values 0.75 / 0.50 / 0.35)
        if final_score >= settings.acif_context_keep_threshold:
            decision = "keep"
        elif final_score >= settings.acif_context_verify_threshold:
            decision = "keep_with_verification"
        elif final_score >= settings.acif_context_min_threshold:
            decision = "use_only_if_no_better_context"
        else:
            decision = "reject"

        return {
            "chunk_id": chunk.get("chunk_id"),
            "score": final_score,
            "decision": decision,
            "dimensions": {
                "semantic_relevance": similarity * 0.25,
                "official_source": 1.0 if is_approved else 0.0,
                "intent_match": intent_score,
            },
            "decision_inputs": {
                "similarity_raw": raw_similarity,
                "similarity_clamped": similarity,
                "intent_match_raw": intent_score,
                "no_contradiction_awarded": graph_awarded,
                "exact_term_bonus_applied": bonus_applied,
                "section_match_bonus_applied": section_match,
            },
        }

    @staticmethod
    def _has_injection(text: str) -> bool:
        """Injection check for a retrieved chunk — reuses RiskSignals.ALL_PHRASES (the same
        phrase list Gate 1 checks the user's own message against) instead of a small,
        separately-maintained 5-phrase list that had drifted far out of sync with Gate 1's
        (CLAUDE.md: no parallel mechanisms for the same detection job)."""
        text_lower = text.lower()
        return any(phrase in text_lower for phrase in RiskSignals.ALL_PHRASES)
