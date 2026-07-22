"""Facade for the Query Understanding Layer.

Pure CPU work (no DB, no LLM, no network). Any internal failure degrades to a minimal
pass-through analysis whose only rewritten query is the original message — i.e. exactly
the pipeline behavior that existed before this layer.
"""
import logging

from app.services.query_understanding.acronym_expander import AcronymExpander
from app.services.query_understanding.conversation_context_resolver import (
    ConversationContextResolver,
)
from app.services.query_understanding.domain_terms_loader import load_domain_terms
from app.services.query_understanding.intent_query_rewriter import (
    IntentClassifier,
    IntentQueryRewriter,
)
from app.services.query_understanding.normalizer import QueryNormalizer
from app.services.query_understanding.schemas import QueryAnalysis
from app.services.query_understanding.synonym_mapper import SynonymMapper

logger = logging.getLogger(__name__)

_SHORT_QUERY_MAX_TOKENS = 3

_INDONESIAN_STOPWORDS = {"yang", "dan", "untuk", "dengan", "adalah", "apa", "bagaimana", "saya", "ini", "itu"}
_ENGLISH_STOPWORDS = {"the", "is", "are", "what", "how", "when", "where", "please", "you", "can"}


class QueryUnderstandingService:
    @staticmethod
    async def analyze(
        message: str,
        history: list[dict] | None = None,
        history_allowed: bool = False,
    ) -> QueryAnalysis:
        try:
            return QueryUnderstandingService._analyze(message, history, history_allowed)
        except Exception as exc:  # fail-safe: never break the chat pipeline
            logger.error("Query understanding failed, using pass-through analysis: %s", exc)
            return QueryAnalysis(
                original_question=message,
                normalized_question=message,
                resolved_question=message,
                rewritten_queries=[message],
                notes="query_understanding_error",
            )

    @staticmethod
    def _analyze(message: str, history: list[dict] | None, history_allowed: bool) -> QueryAnalysis:
        terms = load_domain_terms()
        normalized = QueryNormalizer.normalize(message)
        if not normalized:
            return QueryAnalysis(
                original_question=message,
                normalized_question=message,
                resolved_question=message,
                rewritten_queries=[message],
                notes="empty_after_normalization",
            )

        mapper = SynonymMapper(terms)
        classifier = IntentClassifier(terms)
        concepts = mapper.map_terms(normalized)
        intent, confidence = classifier.classify(normalized, concepts)

        resolver = ConversationContextResolver(terms)
        resolution = resolver.resolve(normalized, history, history_allowed, intent_hint=intent)
        resolved = resolution.resolved_question

        expander = AcronymExpander(terms)
        expansion = expander.expand(resolved)

        # Re-derive concepts/intent from the resolved question when context was added
        # ("syaratnya apa" + spmb now carries the topic).
        if resolution.context_used:
            concepts = mapper.map_terms(resolved)
            intent, confidence = classifier.classify(resolved, concepts)

        variant = mapper.variant_query(resolved, concepts)
        rewritten = IntentQueryRewriter.rewrite(
            resolved_question=resolved,
            expanded_query=expansion.expanded_query,
            expanded_terms=expansion.expanded_terms,
            concepts=concepts,
            intent=intent,
            variant_query=variant,
        )

        detected_terms = expansion.detected_acronyms + [c for c in concepts if c not in expansion.detected_acronyms]

        return QueryAnalysis(
            original_question=message,
            normalized_question=normalized,
            resolved_question=resolved,
            detected_terms=detected_terms,
            expanded_terms=expansion.expanded_terms,
            term_expansions=expansion.term_expansions,
            intent=intent,
            intent_confidence=confidence,
            rewritten_queries=rewritten,
            is_short_query=len(normalized.split()) <= _SHORT_QUERY_MAX_TOKENS,
            exact_term_matched=bool(expansion.detected_acronyms),
            needs_clarification=resolution.needs_clarification,
            clarification_question=resolution.clarification_question,
            context_used=resolution.context_used,
            language=QueryUnderstandingService._detect_language(normalized),
            topic=IntentClassifier.detect_topic(resolved),
            notes="ok",
        )

    @staticmethod
    def _detect_language(normalized: str) -> str:
        """ID-first heuristic mirroring agents.query_understanding_agent."""
        words = normalized.split()
        id_count = sum(1 for w in words if w in _INDONESIAN_STOPWORDS)
        en_count = sum(1 for w in words if w in _ENGLISH_STOPWORDS)
        return "en" if en_count > id_count else "id"
