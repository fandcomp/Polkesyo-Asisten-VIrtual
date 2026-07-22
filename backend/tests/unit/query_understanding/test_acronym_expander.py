"""Tests for AcronymExpander."""
from app.services.query_understanding.acronym_expander import AcronymExpander
from app.services.query_understanding.domain_terms_loader import (
    AcronymEntry,
    DomainTerms,
)

_TERMS = DomainTerms(
    acronyms={
        "spmb": AcronymEntry(
            expansion="seleksi penerimaan mahasiswa baru",
            aliases=("pmb", "penerimaan mahasiswa baru"),
        ),
        "ukt": AcronymEntry(expansion="uang kuliah tunggal"),
    }
)


def test_expands_known_acronym():
    result = AcronymExpander(_TERMS).expand("apa itu spmb")
    assert result.detected_acronyms == ["spmb"]
    assert result.expanded_query == "apa itu spmb seleksi penerimaan mahasiswa baru"
    assert "seleksi penerimaan mahasiswa baru" in result.expanded_terms


def test_whole_token_only_no_substring_match():
    result = AcronymExpander(_TERMS).expand("spmbx apa itu")
    assert result.detected_acronyms == []
    assert result.expanded_query == "spmbx apa itu"


def test_no_double_expansion_when_expansion_already_present():
    query = "spmb seleksi penerimaan mahasiswa baru itu apa"
    result = AcronymExpander(_TERMS).expand(query)
    assert result.detected_acronyms == ["spmb"]
    assert result.expanded_query == query


def test_multiple_acronyms():
    result = AcronymExpander(_TERMS).expand("biaya ukt spmb")
    assert set(result.detected_acronyms) == {"ukt", "spmb"}
    assert "uang kuliah tunggal" in result.expanded_query
    assert "seleksi penerimaan mahasiswa baru" in result.expanded_query


def test_empty_terms_is_noop():
    result = AcronymExpander(DomainTerms()).expand("apa itu spmb")
    assert result.detected_acronyms == []
    assert result.expanded_query == "apa itu spmb"


def test_aliases_included_in_expanded_terms():
    result = AcronymExpander(_TERMS).expand("apa itu spmb")
    assert "pmb" in result.expanded_terms
