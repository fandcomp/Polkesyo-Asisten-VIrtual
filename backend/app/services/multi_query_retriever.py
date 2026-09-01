"""Multi-query vector retrieval with dedup and reranking.

Runs every rewritten query from the Query Understanding Layer against the approved-only
active collection, merges by chunk_id, and reranks. Only APPROVED chunks can ever be
returned because the underlying VectorIndexService searches the active collection —
this module adds recall and ordering, never new sources.

Fail-safe: any internal error degrades to single-query retrieval on the resolved
question (the pre-upgrade behavior).
"""
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
# Reused detectors — the same regexes graph_service uses to extract Biaya/Jadwal entities,
# not new detection logic (CLAUDE.md: no parallel mechanisms).
from app.services.bm25_index import BM25Index
from app.services.graph_service import _BIAYA_RE, _DATE_RE
from app.services.query_understanding.schemas import QueryAnalysis
from app.services.reranker_service import RerankerService
from app.services.vector_retriever import VectorRetrieverService

logger = logging.getLogger(__name__)

# Rerank weights — semantic similarity dominates; exact/expanded term matches reward
# chunks that literally discuss the detected domain terms; approval and graph support
# corroborate. Kept as module constants (not settings): they shape ordering, not gating.
# WEIGHT_SEMANTIC trimmed from 0.40 to make room for WEIGHT_BM25 — hybrid dense+lexical
# retrieval fused by rank position (RRF-style) is the standard fix for dense embeddings
# under-ranking a chunk that literally contains the answer's exact terms (e.g. "tinggi
# badan", "Rp 300.000") beneath a same-document boilerplate chunk that merely uses similar
# formal vocabulary — found live via gold-QA evaluation, confirmed by 2026 RAG literature.
# WEIGHT_SEMANTIC trimmed again, 0.30 -> 0.15, to make room for WEIGHT_RERANKER (2026-07-26):
# a direct Chroma query (bi-encoder cosine similarity only, bypassing BM25/heuristics
# entirely) found the chunk literally containing a question's answer ("Biaya pendaftaran
# sebesar Rp 300.000...") absent from the top 100 candidates — the bi-encoder pools the whole
# chunk into one vector, and a long, multi-topic chunk dilutes the one sentence that matters.
# A cross-encoder (RerankerService) scores (query, chunk) jointly instead, which doesn't
# suffer this dilution — kept as a separate signal rather than replacing WEIGHT_SEMANTIC
# outright since the bi-encoder score is still cheap corroborating evidence when it does agree.
WEIGHT_SEMANTIC = 0.15
WEIGHT_RERANKER = 0.25
WEIGHT_BM25 = 0.15
WEIGHT_EXACT_TERM = 0.20
WEIGHT_EXPANDED_TERM = 0.15
WEIGHT_APPROVED = 0.10
WEIGHT_FRESHNESS = 0.05
WEIGHT_GRAPH_SUPPORT = 0.10
# Intent-aware bonuses (additive, ordering-only): a fee question should prefer the Pedoman
# chunk that holds the fee table over a same-similarity "Hasil Seleksi" announcement.
# Max combined bonus (0.18) stays below WEIGHT_SEMANTIC so low-relevance chunks can't
# leapfrog on document type alone. ACIF Gate 2/3 still gate everything downstream.
WEIGHT_INTENT_DOCTYPE = 0.08
WEIGHT_INTENT_FIGURE = 0.10
# Table-of-contents/preamble chunks (dot-leader lines "Jadwal ..... 13") advertise every
# topic of their document without containing any of the facts — after summaries went
# Indonesian they started outranking the content chunks they point to.
WEIGHT_TOC_PENALTY = 0.10
# Jalur-name disambiguation (2026-07-25): five real jalur pendaftaran share enough
# vocabulary ("Mandiri", "SPMB", "pendaftaran") that neither semantic similarity nor BM25
# reliably separates them — found via gold-QA evaluation (Q002 "...Jalur Mandiri Reguler
# SMA..." retrieved zero chunks from that jalur's own document across all top-5 candidates,
# every single run; same pattern on Q004/Q005/Q008/Q011/Q014). None of the existing rerank
# signals check whether a chunk's SOURCE DOCUMENT is actually about the specific jalur the
# question names. Fixed with a symmetric bonus/penalty: if the question names exactly one
# jalur qualifier and the chunk's document_title names a *different* one, that's positive
# evidence of a wrong-jalur chunk, not just "no evidence for this one" — same magnitude as
# WEIGHT_INTENT_DOCTYPE so it can't alone override a strong semantic match, but is enough to
# break exactly the kind of near-tie this bug exploited.
WEIGHT_JALUR_MATCH = 0.12
WEIGHT_JALUR_MISMATCH = 0.12
# Verified 2026-07-25 against the 5 real jalur documents' actual `documents.title` rows
# (queried live, not guessed) -- e.g. the Profesi document's real title is "Hasi Seleksi
# Tahap II SPMB Profesi Gelombang I 2026" (no "Mandiri" in it at all), so "mandiri profesi"
# would never have matched; "profesi" alone is what actually appears and is still unique
# across all 5 titles. "Mandiri" itself is deliberately excluded from this list -- it's
# shared by multiple jalur names and would defeat the whole point of disambiguating them.
_JALUR_QUALIFIERS: tuple[str, ...] = ("reguler sma", "profesi", "mandiri rpl", "str rpl", "prestasi", "bersama")

# A detected_term whose corpus document frequency exceeds this ratio is excluded from
# WEIGHT_EXACT_TERM eligibility — it matches too much of the collection to discriminate
# relevant from irrelevant chunks. Found via gold-QA trace (Q001, "syarat tinggi badan"):
# detected_terms=['spmb', 'persyaratan']; "spmb" alone has document frequency ~0.59 in this
# corpus (BM25Index.term_document_frequency_ratio), so `any(term in content_tokens ...)`
# awarded the identical +0.20 to every "spmb"-mentioning candidate regardless of true
# relevance, while several noise chunks that matched only "spmb" (not the discriminating
# "persyaratan") outranked the correct chunk into 11th place — one slot outside the top-10
# candidate window. 0.50 was chosen empirically from this corpus's actual term-frequency
# distribution (see investigation notes): domain-wide acronyms/topic words ("spmb" 0.59,
# "pendaftaran" 0.50) sit clearly above it, while genuinely discriminating requirement/
# fact terms ("persyaratan" 0.07, "jadwal" 0.10, "tertib" 0.19, "berharga" 0.01) sit well
# below it — not a per-term hardcode, so it generalizes to any future corpus/vocabulary.
EXACT_TERM_MAX_DOC_FREQUENCY = 0.50

# Which document types most plausibly answer each intent (7-category taxonomy, §21.3).
# "schedule" deliberately excludes Pengumuman: this corpus is dominated by result
# announcements that mention dates constantly; registration timetables live in Pedoman.
_INTENT_DOCTYPE_PREFERENCE: dict[str, set[str]] = {
    "fee": {"Pedoman", "Brosur SPMB"},
    "schedule": {"Pedoman", "Brosur SPMB"},
    "requirement": {"Pedoman", "Regulasi", "Brosur SPMB"},
    "document_requirement": {"Pedoman", "Regulasi", "Brosur SPMB"},
    "form_request": {"Form"},
    "announcement": {"Pengumuman"},
    "procedure": {"SOP", "Pedoman"},
}

# Fallback when the classifier returned "unknown" but a topic keyword was detected.
_TOPIC_TO_INTENT: dict[str, str] = {
    "biaya": "fee",
    "jadwal": "schedule",
    "persyaratan": "requirement",
    "form": "form_request",
    "hasil_seleksi": "announcement",
}

# Figure detectors per intent: a chunk that literally contains an Rp amount (fee) or a
# date/date-range (schedule) is direct evidence it can answer the question.
_INTENT_FIGURE_RE = {
    "fee": _BIAYA_RE,
    "schedule": _DATE_RE,
}


class MultiQueryRetriever:
    @staticmethod
    async def retrieve(
        analysis: QueryAnalysis,
        db: AsyncSession | None,
        cache_service,
        graph_results: list[dict] | None = None,
        top_k_per_query: int | None = None,
    ) -> list[dict]:
        try:
            return await MultiQueryRetriever._retrieve(
                analysis, db, cache_service, graph_results or [], top_k_per_query
            )
        except Exception as exc:
            logger.error("Multi-query retrieval failed, falling back to single query: %s", exc)
            try:
                return await VectorRetrieverService.retrieve(analysis.resolved_question, db=db)
            except Exception as fallback_exc:
                # Retrieval must never crash the chat pipeline — an empty result routes
                # to the controlled insufficient-context fallback downstream.
                logger.error("Single-query fallback retrieval also failed: %s", fallback_exc)
                return []

    @staticmethod
    async def _retrieve(
        analysis: QueryAnalysis,
        db: AsyncSession | None,
        cache_service,
        graph_results: list[dict],
        top_k_per_query: int | None,
    ) -> list[dict]:
        queries = analysis.rewritten_queries or [analysis.resolved_question]
        # Figure-seeking intents (fee/schedule) use the broad pool: the chunk holding the
        # actual figures often sits just below the narrow top-k on raw similarity (the
        # corpus is announcement-dominated) and only wins after the intent-aware rerank
        # bonuses — which can't act on a candidate that never entered the pool. Same
        # rationale applies to requirement-type questions: gold-QA evaluation found the
        # specific fact-bearing chunk (e.g. the height/health-requirement passage) losing
        # out at narrow top-k=5 to a same-document boilerplate/preamble chunk that ranks
        # higher on raw semantic similarity alone, only for the requirement chunk to score
        # higher once exact-term matching entered the rerank — but it never got the chance
        # because it wasn't in the candidate pool.
        top_k = top_k_per_query or (
            settings.rag_top_k_broad
            if (
                analysis.is_short_query
                or analysis.intent_confidence < 0.5
                or analysis.intent in _INTENT_FIGURE_RE
                or analysis.intent in ("requirement", "document_requirement")
            )
            else settings.rag_top_k
        )

        merged: dict[str, dict] = {}
        hits_per_query: list[int] = []
        for query in queries:
            results = None
            if cache_service:
                results = await cache_service.get_vector_retrieval(query, top_k=top_k)
            if results is None:
                results = await VectorRetrieverService.retrieve(query, top_k=top_k, db=db)
                if cache_service and results:
                    await cache_service.set_vector_retrieval(query, results, top_k=top_k)
            hits_per_query.append(len(results))

            for result in results:
                chunk_id = result.get("chunk_id")
                if not chunk_id:
                    continue
                existing = merged.get(chunk_id)
                if existing is None:
                    result = dict(result)
                    result["matched_queries"] = 1
                    merged[chunk_id] = result
                else:
                    existing["matched_queries"] += 1
                    # Keep the best similarity seen across queries.
                    if (result.get("similarity_score") or 0) > (existing.get("similarity_score") or 0):
                        existing["similarity_score"] = result.get("similarity_score")

            # Lexical (BM25) pass over the same query, merged into the same candidate pool —
            # this is what lets a chunk dense search never surfaced (e.g. ranked below top-8
            # on cosine similarity) still enter the pool on the strength of an exact term
            # match. `bm25_rank` (0-indexed, best/lowest across queries) is kept for
            # debugging/logging; `bm25_score` (best/highest raw score across queries) is what
            # actually drives WEIGHT_BM25 in _rerank_score — see the comment there for why
            # rank was replaced with a score-ratio signal.
            if db is not None:
                bm25_results = await BM25Index.search(db, query, top_k=top_k)
                for rank, result in enumerate(bm25_results):
                    chunk_id = result.get("chunk_id")
                    if not chunk_id:
                        continue
                    existing = merged.get(chunk_id)
                    if existing is None:
                        result = dict(result)
                        result["matched_queries"] = 1
                        result["bm25_rank"] = rank
                        result.setdefault("similarity_score", 0.0)
                        merged[chunk_id] = result
                    else:
                        existing["matched_queries"] += 1
                        if existing.get("bm25_rank") is None or rank < existing["bm25_rank"]:
                            existing["bm25_rank"] = rank
                        if (result.get("bm25_score") or 0.0) > (existing.get("bm25_score") or 0.0):
                            existing["bm25_score"] = result.get("bm25_score")

        graph_entities = [
            (g.get("entity_name") or "").lower() for g in graph_results if g.get("entity_name")
        ]
        # Normalize BM25 by score ratio against the strongest lexical match in *this* candidate
        # pool (not a global constant) — see _rerank_score's comment for why this replaced a
        # rank-based signal.
        max_bm25_score = max((c.get("bm25_score") or 0.0) for c in merged.values()) if merged else 0.0

        # Cross-encoder rerank pass over the whole merged pool in one batched call (cheaper
        # than per-candidate calls, and RerankerService.score_pairs is already thread-offloaded
        # + timeout-bounded). Scored against the resolved (canonical, non-rewritten) question —
        # rewritten queries exist to widen vector/BM25 recall, but the cross-encoder should
        # judge relevance against what the user actually asked.
        reranker_scores_by_id: dict[str, float] = {}
        if merged:
            chunk_ids = list(merged.keys())
            texts = [merged[cid].get("content") or "" for cid in chunk_ids]
            raw_scores = await RerankerService.score_pairs(analysis.resolved_question, texts)
            if raw_scores is not None:
                lo, hi = min(raw_scores), max(raw_scores)
                span = hi - lo
                for cid, raw in zip(chunk_ids, raw_scores):
                    # Min-max normalize within this pool (same rationale as the BM25
                    # ratio-to-max signal above) — a raw cross-encoder logit isn't bounded to
                    # [0, 1] and isn't comparable across different candidate pools/queries, but
                    # relative ordering within one pool is exactly what reranking needs.
                    reranker_scores_by_id[cid] = ((raw - lo) / span) if span > 0 else 0.5

        for chunk_id, chunk in merged.items():
            chunk["rerank_score"] = MultiQueryRetriever._rerank_score(
                chunk, analysis, graph_entities, max_bm25_score,
                reranker_scores_by_id.get(chunk_id),
            )

        ranked = sorted(merged.values(), key=lambda c: c["rerank_score"], reverse=True)
        limit = settings.rag_top_k * 2
        logger.debug(
            "Multi-query retrieval: %d queries %s -> hits_per_query=%s merged=%d kept=%d",
            len(queries), queries, hits_per_query, len(merged), min(len(ranked), limit),
        )
        return ranked[:limit]

    @staticmethod
    def _rerank_score(
        chunk: dict, analysis: QueryAnalysis, graph_entities: list[str], max_bm25_score: float = 0.0,
        reranker_signal: float | None = None,
    ) -> float:
        content = (chunk.get("content") or "").lower()
        content_tokens = set(re.findall(r"\w+", content))
        metadata = chunk.get("metadata") or {}

        similarity = max(0.0, min(1.0, chunk.get("similarity_score") or 0.0))

        # Score-ratio signal from the BM25 lexical pass: this chunk's raw score relative to the
        # strongest lexical match in the candidate pool. Zero for chunks the lexical pass never
        # matched.
        #
        # This replaced an earlier reciprocal-rank signal (1.0/(1+bm25_rank)) after gold-QA
        # evaluation (Q016, "tata tertib ujian CBT" consequence question) found it amplifying
        # noise: a document's own title/header chunk and the chunk holding the actual answer
        # scored within ~7% of each other on raw BM25 (both repeat "tata tertib", "ujian",
        # "SPMB" — the header because that vocabulary *is* the document's title, the answer
        # chunk because it's discussing the same rule) — a near-tie any reasonable observer
        # would call noise-level. But reciprocal rank turns "adjacent, nearly-tied ranks" into
        # a large score gap (rank 0 -> 1.0 vs rank 2 -> 0.33), enough by itself to bury the
        # correct chunk. A ratio-to-max signal keeps near-tied raw scores near-tied
        # (e.g. 0.93 vs 1.0) and still rewards a genuinely dominant lexical match (the
        # "tinggi badan" case this index was built for) with a signal close to 1.0 while
        # weaker matches trail proportionally — i.e. it preserves BM25's intended job
        # (surface the chunk with the standout literal term match) without magnifying
        # essentially-tied candidates into a false ordering.
        bm25_score = chunk.get("bm25_score")
        bm25_signal = (bm25_score / max_bm25_score) if bm25_score and max_bm25_score > 0 else 0.0

        exact_term = MultiQueryRetriever._exact_term_eligible_match(content_tokens, analysis.detected_terms)
        expanded_term = any(term in content for term in analysis.expanded_terms)
        approved = metadata.get("status") == "approved"
        # Freshness: neutral 0.5 unless versioned metadata says otherwise (rarely populated).
        freshness = 1.0 if metadata.get("version") else 0.5
        graph_support = any(entity and entity in content for entity in graph_entities)

        return (
            WEIGHT_SEMANTIC * similarity
            + WEIGHT_RERANKER * (reranker_signal if reranker_signal is not None else 0.0)
            + WEIGHT_BM25 * bm25_signal
            + WEIGHT_EXACT_TERM * (1.0 if exact_term else 0.0)
            + WEIGHT_EXPANDED_TERM * (1.0 if expanded_term else 0.0)
            + WEIGHT_APPROVED * (1.0 if approved else 0.0)
            + WEIGHT_FRESHNESS * freshness
            + WEIGHT_GRAPH_SUPPORT * (1.0 if graph_support else 0.0)
            + MultiQueryRetriever._intent_bonus(chunk, analysis)
            + MultiQueryRetriever._jalur_bonus(chunk, analysis)
            - (WEIGHT_TOC_PENALTY if MultiQueryRetriever._looks_like_toc(chunk) else 0.0)
        )

    @staticmethod
    def _exact_term_eligible_match(content_tokens: set[str], detected_terms: list[str]) -> bool:
        """True if a *discriminative* detected term (corpus document frequency at or below
        EXACT_TERM_MAX_DOC_FREQUENCY) matches this chunk's tokens.

        A term whose frequency is unknown (BM25Index not yet built in this process, e.g.
        db=None in unit tests) is treated as eligible — fail open to the pre-fix behavior
        rather than silently zeroing the bonus everywhere. See EXACT_TERM_MAX_DOC_FREQUENCY's
        comment for why this replaced a plain `any(...)` over all detected_terms.
        """
        for term in detected_terms:
            if term not in content_tokens:
                continue
            ratio = BM25Index.term_document_frequency_ratio(term)
            if ratio is None or ratio <= EXACT_TERM_MAX_DOC_FREQUENCY:
                return True
        return False

    @staticmethod
    def _detected_jalur_qualifier(text: str) -> str | None:
        text_lower = text.lower()
        for qualifier in _JALUR_QUALIFIERS:
            if qualifier in text_lower:
                return qualifier
        return None

    @staticmethod
    def _jalur_bonus(chunk: dict, analysis: QueryAnalysis) -> float:
        """Symmetric bonus/penalty for jalur-name disambiguation — see WEIGHT_JALUR_MATCH's
        module-level comment for the bug this fixes. Neutral (0.0) unless the question names
        exactly one jalur qualifier AND the chunk's document_title names exactly one
        (possibly different) qualifier — an unnamed-jalur question or an unnamed-jalur chunk
        stays untouched by this signal."""
        question_jalur = MultiQueryRetriever._detected_jalur_qualifier(analysis.resolved_question or "")
        if question_jalur is None:
            return 0.0
        metadata = chunk.get("metadata") or {}
        document_title = metadata.get("document_title") or ""
        chunk_jalur = MultiQueryRetriever._detected_jalur_qualifier(document_title)
        if chunk_jalur is None:
            return 0.0
        return WEIGHT_JALUR_MATCH if chunk_jalur == question_jalur else -WEIGHT_JALUR_MISMATCH

    @staticmethod
    def _looks_like_toc(chunk: dict) -> bool:
        """Dot-leader lines ("Jadwal Pelaksanaan ..... 13") mark table-of-contents text."""
        haystack = f"{chunk.get('content') or ''}{chunk.get('original_text') or ''}"
        return "......" in haystack

    @staticmethod
    def _intent_bonus(chunk: dict, analysis: QueryAnalysis) -> float:
        """Additive rerank bonus for chunks whose document type / literal figures match
        the question's intent. Zero for intents without a preference — those queries
        rank exactly as before this signal existed."""
        intent = analysis.intent
        if intent not in _INTENT_DOCTYPE_PREFERENCE and analysis.topic:
            intent = _TOPIC_TO_INTENT.get(analysis.topic, intent)

        preferred_types = _INTENT_DOCTYPE_PREFERENCE.get(intent)
        if not preferred_types:
            return 0.0

        bonus = 0.0
        metadata = chunk.get("metadata") or {}
        if metadata.get("document_type") in preferred_types:
            bonus += WEIGHT_INTENT_DOCTYPE

        figure_re = _INTENT_FIGURE_RE.get(intent)
        if figure_re:
            # Search the embedded summary AND the verbatim original — summaries may
            # paraphrase away the literal "Rp 300.000" that the original preserves.
            haystack = f"{chunk.get('content') or ''}\n{chunk.get('original_text') or ''}"
            if figure_re.search(haystack):
                bonus += WEIGHT_INTENT_FIGURE
        return bonus
