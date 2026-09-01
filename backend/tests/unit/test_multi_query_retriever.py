"""Unit tests for MultiQueryRetriever (merge, dedupe, rerank, fail-safe)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.multi_query_retriever import MultiQueryRetriever
from app.services.query_understanding.schemas import QueryAnalysis


def _analysis(**overrides) -> QueryAnalysis:
    defaults = dict(
        original_question="apa itu spmb?",
        normalized_question="apa itu spmb",
        resolved_question="apa itu spmb",
        detected_terms=["spmb"],
        expanded_terms=["seleksi penerimaan mahasiswa baru"],
        rewritten_queries=["apa itu spmb", "apa itu spmb seleksi penerimaan mahasiswa baru"],
        exact_term_matched=True,
        is_short_query=True,
        intent="definition",
        intent_confidence=0.9,
    )
    defaults.update(overrides)
    return QueryAnalysis(**defaults)


@pytest.fixture(autouse=True)
def _no_reranker_by_default():
    """Reranker signal defaults to unavailable (None) for every test in this file, matching
    production's fail-open behavior when the model can't be reached — keeps these unit tests
    hermetic (no model download/network call) and isolates the OTHER rerank signals under
    test. `test_reranker_signal_influences_ranking` overrides this explicitly."""
    with patch(
        "app.services.multi_query_retriever.RerankerService.score_pairs",
        AsyncMock(return_value=None),
    ):
        yield


def _chunk(
    chunk_id: str,
    content: str,
    similarity: float,
    status: str = "approved",
    document_type: str = "",
    original_text: str | None = None,
    document_title: str = "",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "similarity_score": similarity,
        "original_text": original_text,
        "metadata": {"status": status, "document_type": document_type, "document_title": document_title},
    }


@pytest.mark.asyncio
async def test_merges_and_dedupes_across_queries():
    per_query = [
        [_chunk("c1", "info spmb", 0.4), _chunk("c2", "lain", 0.3)],
        [_chunk("c1", "info spmb", 0.6), _chunk("c3", "seleksi penerimaan mahasiswa baru", 0.2)],
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(_analysis(), db=None, cache_service=None)

    ids = [r["chunk_id"] for r in results]
    assert sorted(ids) == ["c1", "c2", "c3"]
    c1 = next(r for r in results if r["chunk_id"] == "c1")
    assert c1["similarity_score"] == 0.6  # max across queries
    assert c1["matched_queries"] == 2


@pytest.mark.asyncio
async def test_exact_term_match_outranks_higher_similarity_without_match():
    per_query = [
        [
            _chunk("no-term", "dokumen umum kampus tanpa istilah relevan", 0.55),
            _chunk("with-term", "informasi spmb poltekkes", 0.35),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(rewritten_queries=["apa itu spmb"]), db=None, cache_service=None
        )

    assert results[0]["chunk_id"] == "with-term"


@pytest.mark.asyncio
async def test_cache_hit_skips_retrieval_for_that_query():
    cache = AsyncMock()
    cache.get_vector_retrieval.side_effect = [[_chunk("cached", "spmb", 0.9)], None]
    cache.set_vector_retrieval = AsyncMock()
    retrieve_mock = AsyncMock(return_value=[_chunk("fresh", "seleksi", 0.5)])

    with patch("app.services.multi_query_retriever.VectorRetrieverService.retrieve", retrieve_mock):
        results = await MultiQueryRetriever.retrieve(_analysis(), db=None, cache_service=cache)

    assert retrieve_mock.await_count == 1  # only the cache-miss query hit Chroma
    assert {r["chunk_id"] for r in results} == {"cached", "fresh"}
    cache.set_vector_retrieval.assert_awaited_once()


@pytest.mark.asyncio
async def test_graph_support_boosts_rerank():
    per_query = [
        [
            _chunk("plain", "informasi umum pendaftaran", 0.5),
            _chunk("graph-backed", "jalur mandiri memerlukan ijazah", 0.5),
        ]
    ]
    graph = [{"entity_type": "JalurPendaftaran", "entity_name": "Jalur Mandiri"}]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(detected_terms=[], expanded_terms=[], rewritten_queries=["syarat jalur mandiri"]),
            db=None,
            cache_service=None,
            graph_results=graph,
        )

    assert results[0]["chunk_id"] == "graph-backed"


@pytest.mark.asyncio
async def test_internal_error_degrades_to_single_query():
    single = [_chunk("c1", "spmb", 0.5)]

    async def _explode(*args, **kwargs):
        raise RuntimeError("boom")

    with patch(
        "app.services.multi_query_retriever.MultiQueryRetriever._retrieve",
        AsyncMock(side_effect=RuntimeError("boom")),
    ), patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(return_value=single),
    ) as fallback_mock:
        results = await MultiQueryRetriever.retrieve(_analysis(), db=None, cache_service=None)

    assert results == single
    fallback_mock.assert_awaited_once_with("apa itu spmb", db=None)


@pytest.mark.asyncio
async def test_fee_intent_prefers_pedoman_fee_chunk_over_announcement():
    """Replay of prod trace 36d30fbd: the Pedoman chunk holding the fee table sat at
    similarity 0.716 (rank 6) while a 'Hasil Seleksi' announcement led at 0.726."""
    per_query = [
        [
            _chunk(
                "hasil-seleksi",
                "pengumuman hasil seleksi jalur mandiri poltekkes",
                0.726,
                document_type="Pengumuman",
            ),
            _chunk(
                "pedoman-biaya",
                "biaya pendaftaran jalur mandiri sebesar Rp 300.000",
                0.716,
                document_type="Pedoman",
            ),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="fee",
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["berapa biaya pendaftaran jalur mandiri"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "pedoman-biaya"


@pytest.mark.asyncio
async def test_fee_figure_in_original_text_counts_when_summary_paraphrases():
    per_query = [
        [
            _chunk("other", "informasi umum biaya kuliah", 0.5, document_type="Pengumuman"),
            _chunk(
                "paraphrased",
                "chunk ini menjelaskan besaran biaya pendaftaran",  # no literal "Rp"
                0.5,
                document_type="Pengumuman",
                original_text="Biaya pendaftaran sebesar Rp 300.000,- dibayarkan via bank.",
            ),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="fee",
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["biaya pendaftaran"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "paraphrased"


@pytest.mark.asyncio
async def test_schedule_intent_boosts_chunk_with_dates():
    per_query = [
        [
            _chunk("no-date", "jadwal akan diumumkan kemudian", 0.55, document_type="FAQ"),
            _chunk(
                "with-date",
                "pendaftaran dibuka 28 April 2026 s/d 10 Juni 2026",
                0.50,
                document_type="Pedoman",
            ),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="schedule",
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["kapan jadwal pendaftaran"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "with-date"


@pytest.mark.asyncio
async def test_topic_fallback_applies_fee_preference_when_intent_unknown():
    per_query = [
        [
            _chunk("announce", "pengumuman kelulusan", 0.6, document_type="Pengumuman"),
            _chunk(
                "pedoman-biaya",
                "rincian biaya sebesar Rp 500.000",
                0.55,
                document_type="Pedoman",
            ),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="unknown",
                topic="biaya",
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["biaya"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "pedoman-biaya"


@pytest.mark.asyncio
async def test_unknown_intent_without_topic_gets_no_intent_bonus():
    """Regression: intents outside the preference map rank purely on the original signals."""
    per_query = [
        [
            _chunk("higher-sim", "konten apa saja", 0.6, document_type="Pedoman",
                   original_text="Rp 100.000"),
            _chunk("lower-sim", "konten lain", 0.5, document_type="Pedoman",
                   original_text="Rp 200.000"),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="unknown",
                topic=None,
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["pertanyaan umum"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "higher-sim"


@pytest.mark.asyncio
async def test_result_count_capped_at_twice_top_k():
    from app.core.config import settings

    many = [[_chunk(f"c{i}", f"konten {i} spmb", 0.5) for i in range(30)]]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=many),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(rewritten_queries=["apa itu spmb"]), db=None, cache_service=None
        )

    assert len(results) <= settings.rag_top_k * 2


@pytest.mark.asyncio
async def test_figure_intents_use_broad_pool():
    """Fee/schedule questions widen the per-query candidate pool so figure-bearing
    chunks ranked just below the narrow top-k can still enter the rerank."""
    from app.core.config import settings

    captured = {}

    async def _capture(query, top_k=None, db=None):
        captured["top_k"] = top_k
        return []

    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=_capture),
    ):
        await MultiQueryRetriever.retrieve(
            _analysis(
                intent="schedule",
                is_short_query=False,
                intent_confidence=0.9,
                rewritten_queries=["kapan pendaftaran dibuka"],
            ),
            db=None,
            cache_service=None,
        )

    assert captured["top_k"] == settings.rag_top_k_broad


@pytest.mark.asyncio
async def test_toc_chunk_penalized_below_content_chunk():
    """A table-of-contents chunk (dot leaders) must not outrank the content chunk
    holding the actual facts it merely points to."""
    per_query = [
        [
            _chunk(
                "toc",
                "daftar isi: jadwal pelaksanaan spmb mandiri",
                0.60,
                document_type="Pedoman",
                original_text="Jadwal Pelaksanaan SPMB Mandiri ................ 13",
            ),
            _chunk(
                "content",
                "jadwal pelaksanaan spmb mandiri pendaftaran 28 April 2026 s/d 10 Juni 2026",
                0.55,
                document_type="Pedoman",
            ),
        ]
    ]
    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                intent="schedule",
                detected_terms=[],
                expanded_terms=[],
                rewritten_queries=["kapan pendaftaran dibuka"],
            ),
            db=None,
            cache_service=None,
        )

    assert results[0]["chunk_id"] == "content"


def test_jalur_bonus_matching_qualifier():
    chunk = _chunk("c1", "info", 0.5, document_title="Pedoman SPMB Mandiri Reguler SMA TA 2026-2027")
    analysis = _analysis(resolved_question="apa syarat tinggi badan spmb jalur mandiri reguler sma")
    from app.services.multi_query_retriever import WEIGHT_JALUR_MATCH, MultiQueryRetriever

    assert MultiQueryRetriever._jalur_bonus(chunk, analysis) == pytest.approx(WEIGHT_JALUR_MATCH)


def test_jalur_bonus_mismatched_qualifier_is_penalized():
    chunk = _chunk("c1", "info", 0.5, document_title="Hasi Seleksi Tahap II SPMB Profesi Gelombang I 2026")
    analysis = _analysis(resolved_question="berapa biaya pendaftaran spmb jalur mandiri reguler sma")
    from app.services.multi_query_retriever import WEIGHT_JALUR_MISMATCH, MultiQueryRetriever

    assert MultiQueryRetriever._jalur_bonus(chunk, analysis) == pytest.approx(-WEIGHT_JALUR_MISMATCH)


def test_jalur_bonus_neutral_when_question_names_no_jalur():
    chunk = _chunk("c1", "info", 0.5, document_title="PEDOMAN SPMB JALUR MANDIRI STR RPL 2026")
    analysis = _analysis(resolved_question="apa saja dokumen yang perlu disiapkan saat daftar ulang")

    assert MultiQueryRetriever._jalur_bonus(chunk, analysis) == pytest.approx(0.0)


def test_jalur_bonus_neutral_when_chunk_document_names_no_jalur():
    chunk = _chunk("c1", "info", 0.5, document_title="PENGUMUMAN HASIL SELEKSI TAHAP II")
    analysis = _analysis(resolved_question="berapa biaya pendaftaran spmb prestasi")

    assert MultiQueryRetriever._jalur_bonus(chunk, analysis) == pytest.approx(0.0)


def test_jalur_bonus_profesi_qualifier_does_not_require_mandiri_prefix():
    """Real title verified 2026-07-25: the Profesi document's actual title has no 'Mandiri'
    in it at all ('Hasi Seleksi Tahap II SPMB Profesi Gelombang I 2026') -- this pins that
    regression down."""
    chunk = _chunk("c1", "info", 0.5, document_title="Hasi Seleksi Tahap II SPMB Profesi Gelombang I 2026")
    analysis = _analysis(resolved_question="apa syarat pendaftaran spmb mandiri profesi")
    from app.services.multi_query_retriever import WEIGHT_JALUR_MATCH, MultiQueryRetriever

    assert MultiQueryRetriever._jalur_bonus(chunk, analysis) == pytest.approx(WEIGHT_JALUR_MATCH)


@pytest.mark.asyncio
async def test_reranker_signal_influences_ranking():
    """2026-07-26 regression pin: a chunk with lower bi-encoder similarity but a dominant
    cross-encoder relevance score (the case found live -- the answer buried in a long,
    multi-topic chunk under-ranks on pooled embedding similarity alone) must be able to
    outrank a higher-similarity chunk the cross-encoder considers less relevant."""
    per_query = [
        [
            _chunk("high-sim-low-relevance", "informasi umum spmb", 0.9),
            _chunk("low-sim-high-relevance", "biaya pendaftaran sebesar Rp 300.000", 0.3),
        ]
    ]

    async def fake_score_pairs(query, texts):
        # Mirrors production ordering (score i matches texts[i]) without depending on dict
        # insertion order -- looks up each text's score explicitly.
        table = {
            "informasi umum spmb": -2.0,
            "biaya pendaftaran sebesar Rp 300.000": 4.0,
        }
        return [table[t] for t in texts]

    with patch(
        "app.services.multi_query_retriever.VectorRetrieverService.retrieve",
        AsyncMock(side_effect=per_query),
    ), patch(
        "app.services.multi_query_retriever.RerankerService.score_pairs",
        AsyncMock(side_effect=fake_score_pairs),
    ):
        results = await MultiQueryRetriever.retrieve(
            _analysis(
                detected_terms=[], expanded_terms=[],
                rewritten_queries=["apa saja biaya pendaftaran spmb"],
            ),
            db=None, cache_service=None,
        )

    assert results[0]["chunk_id"] == "low-sim-high-relevance"
