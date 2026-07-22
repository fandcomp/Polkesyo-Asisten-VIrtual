"""Deterministic intent classification and retrieval-query rewriting.

Injection and out-of-domain detection are NOT decided here — ACIF Gate 1 owns those and
runs on the original input before this layer. Intent labels here drive retrieval breadth,
answer style hints, and evaluation logging only.
"""
from app.services.query_understanding.domain_terms_loader import DomainTerms

# Topic keywords mirror CLAUDE.md §13 / agents.query_understanding_agent — most specific first,
# "pendaftaran" last because its keywords appear in almost every SPMB-related message.
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "jadwal": ["jadwal", "tanggal", "kalender", "gelombang", "tahap", "kapan"],
    "biaya": ["biaya", "bayar", "pembayaran", "tarif", "ukt"],
    "persyaratan": ["syarat", "persyaratan", "dokumen", "berkas"],
    "hasil_seleksi": ["hasil seleksi", "kelulusan", "lulus", "pengumuman"],
    "form": ["form", "formulir", "unduh form"],
    "kontak": ["kontak", "hubungi", "telepon", "email", "alamat"],
    "regulasi": ["pedoman", "tata tertib", "regulasi", "peraturan", "sop", "ketentuan"],
    "pendaftaran": ["daftar", "pendaftaran", "jalur", "spmb", "pmb"],
}

# Fallback intent when only a synonym concept (no question pattern) matched.
_CONCEPT_INTENTS: dict[str, str] = {
    "jadwal": "schedule",
    "biaya": "fee",
    "persyaratan": "requirement",
    "dokumen": "document_requirement",
    "kontak": "contact",
    "formulir": "form_request",
    "pendaftaran": "admin_service",
    # "tertib"/"berharga" map onto "requirement" (not a dedicated "regulation" intent) so
    # they reuse the existing Pedoman/Regulasi/Brosur SPMB doctype preference in
    # multi_query_retriever.py's _INTENT_DOCTYPE_PREFERENCE without adding a new intent
    # bucket that would need its own wiring there.
    "tertib": "requirement",
    "berharga": "requirement",
}

# Retrieval query templates per intent; "{terms}" is filled with expansions/concepts.
_INTENT_TEMPLATES: dict[str, str] = {
    "definition": "pengertian {terms}",
    "schedule": "jadwal {terms}",
    "requirement": "persyaratan {terms}",
    "document_requirement": "dokumen persyaratan {terms}",
    "fee": "biaya {terms}",
    "contact": "kontak layanan {terms}",
    "procedure": "prosedur alur {terms}",
    "form_request": "formulir {terms}",
    "announcement": "pengumuman {terms}",
}

MAX_REWRITTEN_QUERIES = 4

PATTERN_CONFIDENCE = 0.9
CONCEPT_CONFIDENCE = 0.6
UNKNOWN_CONFIDENCE = 0.3


class IntentClassifier:
    def __init__(self, terms: DomainTerms):
        self._terms = terms

    def classify(self, normalized: str, concepts: list[str]) -> tuple[str, float]:
        """Rule-based classification with confidence. Never raises.

        Patterns match as plain substrings (deliberate — this is how the fee/requirement/etc.
        patterns tolerate Indonesian suffixes like "berkas"->"berkasnya", "syarat"->"syaratnya"
        without a stemmer). That tolerance has a failure mode: the bare "harga" (price)
        fee-pattern also matched inside "berharga" (valuable), so "barang berharga"
        (valuables) questions were misclassified as intent="fee" — found via live gold-QA
        retrieval investigation, 2026-07-18. Fixed at the pattern-list level (dropped the
        risky bare "harga" entry, see domain_terms.yaml) rather than switching this method to
        whole-token matching, which regressed the suffix-tolerant cases above (see git history
        of this docstring/tests/unit/query_understanding/test_intent_query_rewriter.py and
        tests/unit/query_understanding/test_query_understanding_service.py).
        """
        for intent, patterns in self._terms.question_patterns.items():
            if any(p in normalized for p in patterns):
                return intent, PATTERN_CONFIDENCE
        for concept in concepts:
            mapped = _CONCEPT_INTENTS.get(concept)
            if mapped:
                return mapped, CONCEPT_CONFIDENCE
        return "unknown", UNKNOWN_CONFIDENCE

    @staticmethod
    def detect_topic(normalized: str) -> str | None:
        for topic, keywords in TOPIC_KEYWORDS.items():
            if any(keyword in normalized for keyword in keywords):
                return topic
        return None


class IntentQueryRewriter:
    @staticmethod
    def rewrite(
        resolved_question: str,
        expanded_query: str,
        expanded_terms: list[str],
        concepts: list[str],
        intent: str,
        variant_query: str | None = None,
    ) -> list[str]:
        """Build 1-4 retrieval queries. The resolved question is always first."""
        queries: list[str] = [resolved_question]

        if expanded_query and expanded_query != resolved_question:
            queries.append(expanded_query)

        template = _INTENT_TEMPLATES.get(intent)
        if template:
            terms = expanded_terms[:1] or [c for c in concepts if c in _CONCEPT_INTENTS] or []
            fill = " ".join(terms) if terms else "penerimaan mahasiswa baru poltekkes"
            templated = template.format(terms=fill).strip()
            if templated not in queries:
                queries.append(templated)

        if variant_query and variant_query not in queries:
            queries.append(variant_query)

        deduped: list[str] = []
        for q in queries:
            q = q.strip()
            if q and q not in deduped:
                deduped.append(q)
        return deduped[:MAX_REWRITTEN_QUERIES]
