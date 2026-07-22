"""Zone-boundary detection patterns for DocumentStructureAgent (structure-aware document
extraction plan).

Keyed by `document_type` — only `"Pedoman"` is registered, matching the verified real
template found by hand-inspecting the production PDF on the VPS (SK Direktur preamble ->
narrative body with lettered sub-bab -> a sequence of divider pages, each opening a zone of
attachment/form pages). Any document_type not in `SUPPORTED_DOCUMENT_TYPES`, or any Pedoman
document whose pages don't actually match these patterns (no divider pages found), produces
zero zones from DocumentStructureAgent — the caller then falls through to today's single
flat-body ingestion path unchanged. This is what makes the rollout safe without first
auditing every document type/instance: a non-matching document simply no-ops.
"""
import re

SUPPORTED_DOCUMENT_TYPES = {"Pedoman"}

# A divider page's stripped text is essentially just one short ALL-CAPS "DOKUMEN ..." heading
# line naming the zone that follows (verified real examples on the ground-truth PDF, pages
# 20/25/29/37: "DOKUMEN PENDAFTARAN", "DOKUMEN UJI KESEHATAN", "DOKUMEN DAFTAR ULANG",
# "DOKUMEN PORTOFOLIO"). Bounded to a short heading (3-40 chars after "DOKUMEN ") so it can't
# match an incidental all-caps sentence buried in ordinary body prose.
DIVIDER_LINE_RE = re.compile(r"^DOKUMEN [A-Z ]{3,40}$")

# SK Direktur (decision-letter) preamble markers. Both must appear on the SAME page to avoid
# a false positive from a page that merely mentions one of the two words in ordinary prose
# elsewhere in the document (e.g. a sub-bab discussing "hal-hal yang perlu diingat"). Case-
# insensitive: real documents render these as title-case field labels ("Menimbang :", not
# "MENIMBANG") — confirmed via Phase 0 profiling (scripts/archive/profile_pedoman_documents.py,
# archived — one-off script, already served its purpose) against
# 3 additional production Pedoman PDFs, where the original case-sensitive all-caps version
# matched zero decision-letter pages on any of them, including the one it was built from.
_MENIMBANG_RE = re.compile(r"\bMENIMBANG\b", re.IGNORECASE)
_MENGINGAT_OR_MENETAPKAN_RE = re.compile(r"\bMENGINGAT\b|\bMENETAPKAN\b", re.IGNORECASE)

# Table-of-contents page — the natural upper bound for the decision-letter zone even when a
# document has more SK-style pages than the ground-truth's 3 (pages 2-4).
_DAFTAR_ISI_RE = re.compile(r"^DAFTAR ISI$")

# A page counts as "essentially blank but for the heading" only up to this many non-blank
# lines — real narrative pages routinely have a heading AND a paragraph underneath it, and
# must NOT be mistaken for a divider (this would otherwise falsely split every lettered
# sub-bab into its own zone).
_MAX_DIVIDER_PAGE_LINES = 3


def is_divider_page(stripped_text: str) -> bool:
    """True if `stripped_text` (a whole page's cleaned text) is a bare zone-divider page."""
    lines = [line.strip() for line in stripped_text.splitlines() if line.strip()]
    if not lines or len(lines) > _MAX_DIVIDER_PAGE_LINES:
        return False
    return any(DIVIDER_LINE_RE.match(line) for line in lines)


def divider_title(stripped_text: str) -> str | None:
    """The divider heading line itself (e.g. "DOKUMEN UJI KESEHATAN"), or None."""
    for line in stripped_text.splitlines():
        line = line.strip()
        if DIVIDER_LINE_RE.match(line):
            return line
    return None


def is_decision_letter_page(stripped_text: str) -> bool:
    """True if this page is part of the SK Direktur legal preamble (Menimbang/Mengingat/
    Menetapkan)."""
    return bool(_MENIMBANG_RE.search(stripped_text) and _MENGINGAT_OR_MENETAPKAN_RE.search(stripped_text))


def is_daftar_isi_page(stripped_text: str) -> bool:
    lines = [line.strip() for line in stripped_text.splitlines() if line.strip()]
    return any(_DAFTAR_ISI_RE.match(line) for line in lines[:5])
