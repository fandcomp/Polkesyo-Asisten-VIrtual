"""Loader for the editable domain vocabulary (app/config/domain_terms.yaml).

Fail-safe by design: a missing or malformed YAML file yields an empty ``DomainTerms``,
which makes every downstream component a no-op — the chat pipeline then behaves exactly
as it did before the Query Understanding Layer existed.
"""
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).parents[2] / "config" / "domain_terms.yaml"


@dataclass(frozen=True)
class AcronymEntry:
    expansion: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainTerms:
    """Immutable, parsed view of domain_terms.yaml."""

    acronyms: dict[str, AcronymEntry] = field(default_factory=dict)
    synonyms: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # Ordered: first matching intent wins, most specific intents listed first in YAML.
    question_patterns: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not (self.acronyms or self.synonyms or self.question_patterns)


def _parse(raw: dict) -> DomainTerms:
    acronyms: dict[str, AcronymEntry] = {}
    for key, value in (raw.get("acronyms") or {}).items():
        if isinstance(value, str):
            acronyms[str(key).lower()] = AcronymEntry(expansion=value.lower())
        elif isinstance(value, dict) and value.get("expansion"):
            acronyms[str(key).lower()] = AcronymEntry(
                expansion=str(value["expansion"]).lower(),
                aliases=tuple(str(a).lower() for a in value.get("aliases") or []),
            )

    synonyms: dict[str, tuple[str, ...]] = {}
    for key, value in (raw.get("synonyms") or {}).items():
        aliases = value.get("aliases") if isinstance(value, dict) else value
        if aliases:
            synonyms[str(key).lower()] = tuple(str(a).lower() for a in aliases)

    question_patterns: dict[str, tuple[str, ...]] = {}
    for intent, value in (raw.get("question_patterns") or {}).items():
        patterns = value.get("patterns") if isinstance(value, dict) else value
        if patterns:
            question_patterns[str(intent)] = tuple(str(p).lower() for p in patterns)

    return DomainTerms(acronyms=acronyms, synonyms=synonyms, question_patterns=question_patterns)


@lru_cache(maxsize=4)
def load_domain_terms(path: str | None = None) -> DomainTerms:
    """Load and cache the domain vocabulary. Never raises."""
    file_path = Path(path) if path else _DEFAULT_PATH
    try:
        with open(file_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError("domain_terms.yaml root must be a mapping")
        return _parse(raw)
    except Exception as exc:  # fail-safe: degrade to pass-through behavior
        logger.error("Failed to load domain terms from %s: %s", file_path, exc)
        return DomainTerms()
