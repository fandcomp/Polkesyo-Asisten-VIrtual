"""Cross-encoder reranking for retrieved chunk candidates.

Dense embedding similarity (bi-encoder: query and chunk embedded separately, then compared
by cosine distance) was found via live gold-QA evaluation to under-rank chunks whose answer
is a specific sentence buried inside a longer, topically-mixed chunk -- the pooled embedding
of the whole chunk dilutes that one sentence's contribution. A cross-encoder scores (query,
chunk) as a single joint input, which captures fine-grained relevance a bi-encoder's
independently-pooled vectors cannot. See config.py's reranker_* settings for the model choice
rationale (CPU-only, small multilingual MiniLM).

Fail-safe by design: any load or scoring failure returns None (see `score_pairs`), and
callers must treat that as "no reranker signal" rather than raising -- retrieval must degrade
to its pre-reranker behavior, never crash the chat pipeline.
"""
import asyncio
import logging
import threading

from app.core.config import settings

logger = logging.getLogger(__name__)

_cross_encoder = None
_cross_encoder_loaded = False
# Same warm-up race concern as VectorIndexService._embedding_function_lock: without this,
# concurrent asyncio.to_thread callers each see _cross_encoder_loaded=False and load their
# own CrossEncoder simultaneously.
_cross_encoder_lock = threading.Lock()


class RerankerService:
    """Score (query, chunk_text) pairs with a cross-encoder for retrieval reranking."""

    @staticmethod
    def get_cross_encoder():
        """Lazily load the configured cross-encoder model (cached per process).

        A load failure logs CRITICAL and leaves the encoder as None permanently for this
        process -- callers must check for None and skip the reranker signal rather than
        retrying per-request (a broken model name would otherwise retry-and-fail on every
        single chat request)."""
        global _cross_encoder, _cross_encoder_loaded
        if _cross_encoder_loaded:
            return _cross_encoder
        with _cross_encoder_lock:
            if _cross_encoder_loaded:
                return _cross_encoder
            if settings.reranker_enabled and settings.reranker_model_name.strip():
                try:
                    from sentence_transformers import CrossEncoder

                    _cross_encoder = CrossEncoder(settings.reranker_model_name.strip())
                except Exception as exc:
                    logger.critical(
                        "Failed to load reranker model %s -- reranking disabled for this "
                        "process, retrieval falls back to pre-reranker ordering: %s",
                        settings.reranker_model_name, exc,
                    )
                    _cross_encoder = None
            _cross_encoder_loaded = True
        return _cross_encoder

    @staticmethod
    def _predict_sync(query: str, texts: list[str]) -> list[float]:
        """Blocking cross-encoder inference -- must run in a thread (same rationale as
        Chroma calls: a CPU-bound blocking call in an async def freezes the whole worker's
        event loop, not just this request)."""
        encoder = RerankerService.get_cross_encoder()
        if encoder is None:
            return [0.0] * len(texts)
        pairs = [(query, text) for text in texts]
        scores = encoder.predict(pairs)
        return [float(s) for s in scores]

    @staticmethod
    async def score_pairs(query: str, texts: list[str]) -> list[float] | None:
        """Score `texts` against `query`, returning one raw cross-encoder score per text in
        the same order. Returns None (not a list of zeros) on failure/timeout/disabled, so
        callers can distinguish "no signal available" from "genuinely scored as irrelevant"
        and skip the reranker weight entirely rather than penalizing every candidate."""
        if not settings.reranker_enabled or not texts:
            return None
        timeout = settings.reranker_timeout_seconds * max(1, len(texts) // 10 + 1)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(RerankerService._predict_sync, query, texts),
                timeout=timeout,
            )
        except Exception as exc:
            logger.warning("Reranker scoring failed/timed out, skipping reranker signal: %s", exc)
            return None
