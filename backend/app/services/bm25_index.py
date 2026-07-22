"""In-process BM25 (Okapi) lexical index over approved chunks — complements Chroma's dense
vector search in MultiQueryRetriever via Reciprocal Rank Fusion (RRF).

Why this exists: gold-QA evaluation found dense vector search alone missing the correct chunk
even in a top-10 candidate pool when a document's generic preamble/boilerplate text scored
higher on semantic similarity than the chunk literally containing the answer (e.g. "Tinggi
badan dengan ketentuan..." for a height-requirement question). This is a well-documented dense-
retrieval failure mode — administrative/legal text is semantically homogeneous, so embeddings
alone can't reliably rank a chunk mentioning a specific fact above one that just uses similar
formal vocabulary. Hybrid lexical + dense retrieval, fused via RRF, is the standard fix (BM25
catches exact/rare term matches like "tinggi badan" or "Rp 300.000" that embeddings underweight;
RRF combines the two rankings by rank position rather than raw score, avoiding the scale-
mismatch problem of averaging an unbounded BM25 score with a 0-1 cosine similarity).

No new dependency: BM25 is a small, well-defined formula (Robertson/Sparck Jones), implemented
here directly rather than adding rank_bm25 to pyproject.toml and rebuilding the image for it.

Indexes `original_text` (the immutable, verbatim source — CLAUDE.md's citation-evidence text),
not the LLM-generated summary that Chroma indexes: BM25's whole value is exact lexical matching,
and a paraphrased summary can lose the literal term a question is looking for.
"""
import logging
import math
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChunkSummary, Document, DocumentChunk
from app.services.text_extractor import TextExtractor

logger = logging.getLogger(__name__)

# Standard Okapi BM25 constants (Robertson et al.) — k1 controls term-frequency saturation,
# b controls document-length normalization. These defaults are the widely-used baseline
# (also Elasticsearch/Lucene's default) and are not a tuning target for this fix.
_K1 = 1.5
_B = 0.75

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

# Process-wide cache, same pattern as VectorIndexService's embedding-function singleton —
# rebuilding the index (one query + tokenizing ~300 chunks) is cheap but not free, and this
# runs on every retrieval call otherwise. Rebuilt on next call after `invalidate()`.
_index: "_Bm25Corpus | None" = None


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class _Bm25Corpus:
    """Holds the built index: per-document term frequencies, document frequencies, lengths."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks  # list of {"chunk_id":..., "tokens": Counter, "length": int, "metadata": {...}, "original_text":...}
        self.n_docs = len(chunks)
        self.avg_len = (sum(c["length"] for c in chunks) / self.n_docs) if self.n_docs else 0.0
        # document frequency: how many chunks contain each term at least once
        df: Counter = Counter()
        for c in chunks:
            df.update(c["tokens"].keys())
        self.df = df

    def _idf(self, term: str) -> float:
        n_qi = self.df.get(term, 0)
        # +1 inside the log keeps IDF non-negative even for terms in every document —
        # the standard Lucene/BM25+ variant guard, avoids negative-weight terms dominating.
        return math.log((self.n_docs - n_qi + 0.5) / (n_qi + 0.5) + 1)

    def search(self, query: str, top_k: int) -> list[dict]:
        if self.n_docs == 0:
            return []
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        idf_cache = {term: self._idf(term) for term in set(query_terms)}
        scored = []
        for chunk in self.chunks:
            score = 0.0
            length = chunk["length"] or 1
            for term in query_terms:
                f = chunk["tokens"].get(term, 0)
                if f == 0:
                    continue
                idf = idf_cache[term]
                score += idf * (f * (_K1 + 1)) / (f + _K1 * (1 - _B + _B * length / self.avg_len))
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            {
                "chunk_id": c["chunk_id"],
                "bm25_score": score,
                "metadata": c["metadata"],
                "content": c["original_text"],
                "original_text": c["original_text"],
            }
            for score, c in scored[:top_k]
        ]


async def _build(db: AsyncSession) -> _Bm25Corpus:
    stmt = (
        select(DocumentChunk, ChunkSummary, Document)
        .join(ChunkSummary)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            (DocumentChunk.status == "approved") &
            (ChunkSummary.approved_summary.isnot(None))
        )
    )
    rows = (await db.execute(stmt)).all()

    chunks = []
    for chunk, _summary, document in rows:
        # Clean at index time only — `chunk.original_text` in the DB stays untouched
        # (CLAUDE.md: original chunk text is immutable citation evidence). The near-
        # universal e-signature boilerplate (96.7% of approved chunks) contributes identical
        # term frequencies to almost every document, actively hurting BM25's ability to
        # discriminate between chunks.
        text = TextExtractor._clean_boilerplate(chunk.original_text or "")
        tokens = Counter(_tokenize(text))
        chunks.append({
            "chunk_id": str(chunk.id),
            "tokens": tokens,
            "length": sum(tokens.values()),
            "original_text": text,
            "metadata": {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "document_title": document.title or "",
                "document_type": document.document_type or "",
                "page": chunk.page if chunk.page is not None else -1,
                "section": chunk.section or "",
                "chunk_index": chunk.chunk_index,
                "status": "approved",
            },
        })
    logger.info("BM25Index built: %d approved chunks", len(chunks))
    return _Bm25Corpus(chunks)


class BM25Index:
    """Lexical retrieval over approved chunks — see module docstring for why this exists."""

    @staticmethod
    async def search(db: AsyncSession, query: str, top_k: int = 8) -> list[dict]:
        """Returns up to top_k chunk dicts ranked by BM25 score, shaped like
        VectorRetrieverService.retrieve()'s output so MultiQueryRetriever can merge them."""
        global _index
        try:
            if _index is None:
                _index = await _build(db)
            return _index.search(query, top_k)
        except Exception as exc:
            # Same fail-safe posture as VectorRetrieverService: a lexical-index problem must
            # degrade to vector-only retrieval, never break the chat pipeline.
            logger.error("BM25Index.search failed for query %r: %s", query, exc)
            return []

    @staticmethod
    def term_document_frequency_ratio(term: str) -> float | None:
        """Fraction of the approved corpus (0.0-1.0) containing `term` at least once, or
        None if the index hasn't been built yet in this process (fail-safe — callers should
        treat None as "no signal available", not "rare").

        Reuses the document-frequency counts BM25 already computes for its own IDF
        weighting (`_Bm25Corpus.df`) rather than building a second frequency table —
        MultiQueryRetriever's rerank uses this to down-weight its exact-term bonus for
        domain-wide terms (e.g. "spmb" in this SPMB-only corpus) that match almost every
        candidate and so carry no discriminative signal despite being a literal match.
        """
        if _index is None or _index.n_docs == 0:
            return None
        return _index.df.get(term, 0) / _index.n_docs

    @staticmethod
    def invalidate() -> None:
        """Drop the cached index — call after chunk approval/reindexing changes the approved
        set, so the next search rebuilds from current data. Mirrors the existing
        retrieval-cache invalidation already done on chunk approve (routes_chunk_review.py)."""
        global _index
        _index = None
