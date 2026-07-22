"""Campus acronym detection and expansion (whole-token match only)."""
from dataclasses import dataclass, field

from app.services.query_understanding.domain_terms_loader import DomainTerms


@dataclass(frozen=True)
class ExpansionResult:
    detected_acronyms: list[str] = field(default_factory=list)
    expanded_terms: list[str] = field(default_factory=list)
    expanded_query: str = ""
    # acronym token -> its expansion phrases (for per-word matching in Gate 2)
    term_expansions: dict[str, list[str]] = field(default_factory=dict)


class AcronymExpander:
    def __init__(self, terms: DomainTerms):
        self._terms = terms

    def expand(self, normalized: str) -> ExpansionResult:
        """Detect acronyms as whole tokens and append their expansions to the query.

        "apa itu spmb" -> expanded_query "apa itu spmb seleksi penerimaan mahasiswa baru".
        Never removes the original token, so the expansion can only add retrieval recall.
        """
        tokens = normalized.split()
        detected: list[str] = []
        expanded_terms: list[str] = []
        term_expansions: dict[str, list[str]] = {}
        parts: list[str] = []

        for token in tokens:
            parts.append(token)
            entry = self._terms.acronyms.get(token)
            if entry and token not in detected:
                detected.append(token)
                expanded_terms.append(entry.expansion)
                expanded_terms.extend(a for a in entry.aliases if a not in expanded_terms)
                term_expansions[token] = [entry.expansion, *entry.aliases]
                # Append the canonical expansion right after the acronym token.
                if entry.expansion not in normalized:
                    parts.append(entry.expansion)

        expanded_query = " ".join(parts) if detected else normalized
        return ExpansionResult(
            detected_acronyms=detected,
            expanded_terms=expanded_terms,
            expanded_query=expanded_query,
            term_expansions=term_expansions,
        )
