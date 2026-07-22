"""Tests for IntentClassifier and IntentQueryRewriter."""
from app.services.query_understanding.domain_terms_loader import load_domain_terms
from app.services.query_understanding.intent_query_rewriter import (
    MAX_REWRITTEN_QUERIES,
    IntentClassifier,
    IntentQueryRewriter,
)


def _classifier() -> IntentClassifier:
    load_domain_terms.cache_clear()
    return IntentClassifier(load_domain_terms())


def test_definition_intent():
    intent, confidence = _classifier().classify("apa itu spmb", [])
    assert intent == "definition"
    assert confidence == 0.9


def test_schedule_intent():
    intent, confidence = _classifier().classify("kapan pendaftaran dimulai", [])
    assert intent == "schedule"
    assert confidence == 0.9


def test_requirement_intent():
    intent, _ = _classifier().classify("syarat daftar apa", [])
    assert intent == "requirement"


def test_document_requirement_intent():
    intent, _ = _classifier().classify("berkasnya apa aja", [])
    assert intent == "document_requirement"


def test_contact_intent():
    intent, _ = _classifier().classify("kontak adminnya mana", [])
    assert intent == "contact"


def test_form_request_intent():
    intent, _ = _classifier().classify("minta form pendaftaran", [])
    assert intent == "form_request"


def test_concept_fallback_medium_confidence():
    intent, confidence = _classifier().classify("mau tahu soal pembayaran kuliah", ["biaya"])
    assert intent == "fee"
    assert confidence == 0.6


def test_unknown_low_confidence():
    intent, confidence = _classifier().classify("halo selamat pagi", [])
    assert intent == "unknown"
    assert confidence == 0.3


def test_barang_berharga_does_not_misclassify_as_fee():
    """Regression test, 2026-07-18: "berharga" (valuable) contains "harga" (price) as a
    substring, which used to trigger the fee intent's bare "harga" pattern — found via a
    live gold-QA retrieval failure (Q017, "boleh membawa barang berharga ke ruang ujian?"
    was misclassified as intent=fee, which then boosted fee-figure chunks over the actually
    relevant tata-tertib chunk in multi_query_retriever's rerank). Fixed by dropping the bare
    "harga" pattern rather than by stemming/tokenizing (see classify()'s docstring)."""
    intent, confidence = _classifier().classify(
        "apakah peserta ujian cbt spmb diperbolehkan membawa barang berharga ke ruang ujian",
        ["berharga"],
    )
    assert intent != "fee"
    assert intent == "requirement"
    assert confidence == 0.9


def test_fee_intent_still_detected_via_biaya():
    """"harga" was removed from the fee pattern list, but "biaya"/"berapa biaya"/"tarif"/"ukt"
    must still classify real fee questions correctly."""
    intent, _ = _classifier().classify("berapa biaya pendaftaran spmb", [])
    assert intent == "fee"


def test_tata_tertib_violation_intent():
    """Regression test, 2026-07-18: exam-conduct/regulation questions ("tata tertib",
    "pelanggaran", "konsekuensi") had no domain vocabulary at all, so they fell through to
    intent="unknown" with no exact-term-match bonus in the retriever rerank (Q016 in the gold-QA
    set). New "tertib" concept + requirement pattern entries fix this."""
    intent, confidence = _classifier().classify(
        "apa konsekuensi bagi peserta yang melanggar tata tertib saat ujian cbt spmb",
        ["tertib"],
    )
    assert intent == "requirement"
    assert confidence == 0.9


def test_topic_detection():
    assert IntentClassifier.detect_topic("kapan jadwal daftar") == "jadwal"
    assert IntentClassifier.detect_topic("apa itu spmb") == "pendaftaran"
    assert IntentClassifier.detect_topic("halo") is None


def test_rewrite_includes_resolved_question_first():
    queries = IntentQueryRewriter.rewrite(
        resolved_question="apa itu spmb",
        expanded_query="apa itu spmb seleksi penerimaan mahasiswa baru",
        expanded_terms=["seleksi penerimaan mahasiswa baru"],
        concepts=[],
        intent="definition",
    )
    assert queries[0] == "apa itu spmb"
    assert "apa itu spmb seleksi penerimaan mahasiswa baru" in queries
    assert any(q.startswith("pengertian") for q in queries)


def test_rewrite_caps_and_dedupes():
    queries = IntentQueryRewriter.rewrite(
        resolved_question="jadwal pendaftaran",
        expanded_query="jadwal pendaftaran",
        expanded_terms=["a", "b"],
        concepts=["pendaftaran", "jadwal"],
        intent="schedule",
        variant_query="jadwal pendaftaran",
    )
    assert len(queries) == len(set(queries))
    assert len(queries) <= MAX_REWRITTEN_QUERIES


def test_rewrite_unknown_intent_no_template():
    queries = IntentQueryRewriter.rewrite(
        resolved_question="halo",
        expanded_query="halo",
        expanded_terms=[],
        concepts=[],
        intent="unknown",
    )
    assert queries == ["halo"]
