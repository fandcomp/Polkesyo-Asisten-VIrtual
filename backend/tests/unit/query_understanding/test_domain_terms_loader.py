"""Tests for the domain terms YAML loader (fail-safe behavior included)."""
from app.services.query_understanding.domain_terms_loader import (
    DomainTerms,
    load_domain_terms,
)


def test_loads_bundled_yaml():
    load_domain_terms.cache_clear()
    terms = load_domain_terms()
    assert not terms.is_empty
    assert terms.acronyms["spmb"].expansion == "seleksi penerimaan mahasiswa baru"
    assert "pendaftaran" in terms.synonyms
    assert "definition" in terms.question_patterns


def test_missing_file_returns_empty_terms():
    load_domain_terms.cache_clear()
    terms = load_domain_terms("Z:/does/not/exist.yaml")
    assert isinstance(terms, DomainTerms)
    assert terms.is_empty
    load_domain_terms.cache_clear()


def test_malformed_yaml_returns_empty_terms(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("just a plain string, not a mapping", encoding="utf-8")
    load_domain_terms.cache_clear()
    terms = load_domain_terms(str(bad))
    assert terms.is_empty
    load_domain_terms.cache_clear()


def test_question_patterns_preserve_yaml_order():
    """First matching intent wins, so schedule (specific) must come before definition."""
    load_domain_terms.cache_clear()
    terms = load_domain_terms()
    intents = list(terms.question_patterns)
    assert intents.index("schedule") < intents.index("definition")
