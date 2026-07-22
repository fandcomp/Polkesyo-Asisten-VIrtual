"""Tests for SynonymMapper."""
from app.services.query_understanding.domain_terms_loader import DomainTerms
from app.services.query_understanding.synonym_mapper import SynonymMapper

_TERMS = DomainTerms(
    synonyms={
        "pendaftaran": ("daftar", "daftarnya", "registrasi"),
        "jadwal": ("kapan", "tanggal", "batas akhir"),
        "persyaratan": ("syarat", "syaratnya"),
    }
)


def test_maps_alias_token_to_concept():
    concepts = SynonymMapper(_TERMS).map_terms("daftarnya kapan ya")
    assert "pendaftaran" in concepts
    assert "jadwal" in concepts


def test_concept_word_itself_matches():
    assert SynonymMapper(_TERMS).map_terms("jadwal pendaftaran") == ["pendaftaran", "jadwal"]


def test_multiword_alias_matches_as_substring():
    assert "jadwal" in SynonymMapper(_TERMS).map_terms("batas akhir pendaftaran ulang")


def test_single_word_alias_is_whole_token():
    # "mendaftarkan" contains "daftar" as substring but is not the token "daftar"
    assert SynonymMapper(_TERMS).map_terms("mendaftarkan anak") == []


def test_variant_query_appends_missing_concepts():
    mapper = SynonymMapper(_TERMS)
    variant = mapper.variant_query("daftarnya kapan ya", ["pendaftaran", "jadwal"])
    assert variant == "daftarnya kapan ya pendaftaran jadwal"


def test_variant_query_none_when_concepts_already_present():
    mapper = SynonymMapper(_TERMS)
    assert mapper.variant_query("jadwal pendaftaran", ["pendaftaran", "jadwal"]) is None
