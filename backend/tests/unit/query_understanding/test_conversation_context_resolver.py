"""Tests for ConversationContextResolver (consent-aware follow-up resolution)."""
from app.services.query_understanding.conversation_context_resolver import (
    ConversationContextResolver,
)
from app.services.query_understanding.domain_terms_loader import load_domain_terms


def _resolver() -> ConversationContextResolver:
    load_domain_terms.cache_clear()
    return ConversationContextResolver(load_domain_terms())


_SPMB_HISTORY = [
    {"role": "user", "message": "apa itu spmb?"},
    {"role": "assistant", "message": "SPMB adalah seleksi penerimaan mahasiswa baru."},
]


def test_self_contained_question_untouched():
    result = _resolver().resolve("apa itu spmb", None, history_allowed=False)
    assert result.resolved_question == "apa itu spmb"
    assert not result.needs_clarification
    assert not result.context_used


def test_elliptical_with_history_consent_resolves_topic():
    result = _resolver().resolve("syaratnya apa", _SPMB_HISTORY, history_allowed=True)
    assert result.context_used
    assert "spmb" in result.resolved_question
    assert "seleksi penerimaan mahasiswa baru" in result.resolved_question
    assert not result.needs_clarification


def test_elliptical_without_consent_asks_clarification():
    result = _resolver().resolve(
        "syaratnya apa", _SPMB_HISTORY, history_allowed=False, intent_hint="requirement"
    )
    assert result.needs_clarification
    assert result.clarification_question
    assert "SPMB" in result.clarification_question


def test_elliptical_no_history_asks_clarification():
    result = _resolver().resolve("syaratnya apa", None, history_allowed=True)
    assert result.needs_clarification


def test_registration_topic_is_self_contained():
    # "daftarnya kapan ya" carries the registration topic itself
    result = _resolver().resolve("daftarnya kapan ya", None, history_allowed=False)
    assert not result.needs_clarification
    assert result.resolved_question == "daftarnya kapan ya"


def test_long_question_never_elliptical():
    q = "bagaimana prosedur pengajuan cuti akademik di kampus ini secara lengkap"
    result = _resolver().resolve(q, None, history_allowed=False)
    assert not result.needs_clarification


def test_history_scan_limited_to_last_three_user_turns():
    history = [{"role": "user", "message": "apa itu spmb?"}] + [
        {"role": "user", "message": f"pertanyaan lain {i}"} for i in range(3)
    ]
    result = _resolver().resolve("syaratnya apa", history, history_allowed=True)
    # spmb turn is outside the 3-turn window -> clarification, not a stale guess
    assert result.needs_clarification


def test_intent_specific_clarification_copy():
    result = _resolver().resolve(
        "berkasnya apa aja ya", None, history_allowed=False, intent_hint="document_requirement"
    )
    assert result.needs_clarification
    assert "Berkas" in result.clarification_question
