"""Tests for reason-specific fallback messages."""
from app.services.acif.output_claim_verifier import FallbackResponse
from app.services.fallback_messages import FALLBACK_MESSAGES, get_fallback_message


def test_every_taxonomy_reason_has_indonesian_copy():
    expected = {
        "no_context", "ambiguous_question", "out_of_domain", "prompt_injection",
        "insufficient_context", "conflicting_context", "unapproved_only",
        "retrieval_error", "llm_error",
    }
    assert expected == set(FALLBACK_MESSAGES)
    assert all(msg.strip() for msg in FALLBACK_MESSAGES.values())


def test_unknown_reason_defaults_to_insufficient_context():
    assert get_fallback_message("weird-reason") == FALLBACK_MESSAGES["insufficient_context"]
    assert get_fallback_message(None) == FALLBACK_MESSAGES["insufficient_context"]
    # Gate 5 free-text reasons also map to the default copy
    assert (
        get_fallback_message("Found 2 unsupported critical claim(s)")
        == FALLBACK_MESSAGES["insufficient_context"]
    )


def test_fallback_response_back_compat_constant():
    """Existing callers/tests reference FALLBACK_MESSAGE — it must stay the default copy."""
    assert FallbackResponse.FALLBACK_MESSAGE == FALLBACK_MESSAGES["insufficient_context"]
    assert FallbackResponse.get_fallback() == FALLBACK_MESSAGES["insufficient_context"]


def test_fallback_response_reason_specific():
    assert FallbackResponse.get_fallback("no_context") == FALLBACK_MESSAGES["no_context"]
    assert FallbackResponse.get_fallback("llm_error") == FALLBACK_MESSAGES["llm_error"]


def test_no_internal_details_in_copy():
    """Messages are user-facing: no ACIF terminology, gate numbers, or stack details."""
    for msg in FALLBACK_MESSAGES.values():
        lowered = msg.lower()
        assert "acif" not in lowered
        assert "gate" not in lowered
        assert "error:" not in lowered
