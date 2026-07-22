"""Tests for QueryNormalizer."""
from app.services.query_understanding.normalizer import QueryNormalizer


def test_strips_trailing_question_mark():
    assert QueryNormalizer.normalize("apa itu spmb?") == "apa itu spmb"


def test_lowercases_and_collapses_whitespace():
    assert QueryNormalizer.normalize("  APA   itu   SPMB ") == "apa itu spmb"


def test_punctuation_becomes_space_not_removed():
    # "spmb?itu" must not fuse into one token
    assert QueryNormalizer.normalize("spmb?itu apa") == "spmb itu apa"


def test_preserves_numbers_and_years():
    assert QueryNormalizer.normalize("jadwal SPMB 2026?") == "jadwal spmb 2026"


def test_strips_zero_width_characters():
    assert QueryNormalizer.normalize("spm​b itu apa") == "spmb itu apa"


def test_empty_input():
    assert QueryNormalizer.normalize("") == ""
    assert QueryNormalizer.normalize("   ") == ""


def test_tokens():
    assert QueryNormalizer.tokens("Syaratnya apa?") == ["syaratnya", "apa"]
