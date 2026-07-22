"""Map informal/colloquial phrasing onto canonical domain concepts."""
from app.services.query_understanding.domain_terms_loader import DomainTerms


class SynonymMapper:
    def __init__(self, terms: DomainTerms):
        self._terms = terms

    def map_terms(self, normalized: str) -> list[str]:
        """Return canonical concepts whose alias (or the concept itself) appears in the text.

        Single-word aliases match as whole tokens; multi-word aliases match as substrings.
        """
        tokens = set(normalized.split())
        concepts: list[str] = []
        for concept, aliases in self._terms.synonyms.items():
            if concept in tokens:
                concepts.append(concept)
                continue
            for alias in aliases:
                matched = alias in tokens if " " not in alias else alias in normalized
                if matched:
                    concepts.append(concept)
                    break
        return concepts

    def variant_query(self, normalized: str, concepts: list[str]) -> str | None:
        """Build one query variant with canonical concept words appended.

        "daftarnya kapan ya" + [pendaftaran, jadwal] -> "daftarnya kapan ya pendaftaran jadwal".
        Additive only — informal tokens stay so exact matches still work.
        """
        missing = [c for c in concepts if c not in normalized.split()]
        if not missing:
            return None
        return f"{normalized} {' '.join(missing)}"
