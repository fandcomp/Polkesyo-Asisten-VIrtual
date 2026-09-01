"""ACIF Gate 1 — Input Intent Integrity Checker."""
from app.services.acif.schemas import ACIFGate1Result, ACIFDecision
from app.services.acif.text_normalizer import TextNormalizer
from app.services.acif.risk_signals import RiskSignals
from app.services.acif.semantic_injection_detector import SemanticInjectionDetector
from app.core.config import settings


class InputIntegrityChecker:
    """Check input for prompt injection and domain violations."""

    @staticmethod
    async def check(message: str) -> ACIFGate1Result:
        """Check input message for integrity issues."""

        # Normalize text for analysis
        normalized = TextNormalizer.normalize(message)

        # Check for known risk signals
        risk_score, signals_found = RiskSignals.get_risk_score(normalized)

        # Check for encoded attacks
        encoded_patterns = TextNormalizer.extract_encoded_patterns(message)
        if encoded_patterns:
            risk_score = min(1.0, risk_score + 0.15)
            signals_found.extend(encoded_patterns)

        # Semantic layer: catches paraphrased injection/jailbreak attempts the literal
        # phrase list above cannot (see semantic_injection_detector.py). Embeds the RAW
        # message (not the normalized/lowercased/NFKD-decomposed form above -- the
        # sentence-transformer is case- and punctuation-robust on natural text, and
        # over-normalizing risks degrading embedding quality). None means "no signal
        # available" (disabled/model failure/timeout) -- score_bump(None) is 0.0, so this
        # fails safe to literal-only detection, never blocking on a missing signal.
        semantic_similarity = await SemanticInjectionDetector.max_similarity_to_known_attacks(message)
        semantic_bump = SemanticInjectionDetector.score_bump(semantic_similarity)
        if semantic_bump > 0:
            risk_score = min(1.0, risk_score + semantic_bump)
            signals_found.append(f"semantic_similarity:{semantic_similarity:.2f}")

        # Determine decision based on thresholds from config
        reject_threshold = settings.acif_input_reject_threshold  # default 0.80
        caution_threshold = settings.acif_input_caution_threshold  # default 0.30
        
        if risk_score >= reject_threshold:
            decision = ACIFDecision.REJECT
            reasoning = f"Input contains {len(signals_found)} risk signals exceeding reject threshold"
        elif risk_score >= caution_threshold:
            decision = ACIFDecision.CAUTION
            reasoning = f"Input contains {len(signals_found)} risk signals — proceeding with caution"
        else:
            decision = ACIFDecision.ACCEPT
            reasoning = "Input passes integrity checks"

        # Topical domain validation (CLAUDE.md §12) — separate axis from injection scoring.
        # An injection REJECT takes precedence; otherwise a topic match short-circuits the
        # pipeline to the out-of-domain response before any retrieval or LLM call.
        domain_topics = RiskSignals.get_domain_topic_matches(normalized)
        domain_violation = bool(domain_topics) and decision != ACIFDecision.REJECT
        if domain_violation:
            reasoning = (
                f"{reasoning}; out-of-domain topic detected "
                f"({len(domain_topics)} topic category match)"
            )

        return ACIFGate1Result(
            decision=decision,
            score=risk_score,
            risk_signals=signals_found,
            reasoning=reasoning,
            domain_violation=domain_violation,
            domain_topics=domain_topics,
        )
