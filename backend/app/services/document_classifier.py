"""Classify documents by type based on filename and content hints."""
import re


class DocumentClassifier:
    """Classify documents into types."""

    # Keyword patterns for each type
    TYPE_PATTERNS = {
        "Pengumuman": [
            r"pengumuman",
            r"hasil",
            r"kelulusan",
            r"penerimaan",
            r"announcement",
        ],
        "Pedoman": [
            r"pedoman",
            r"panduan",
            r"guide",
            r"tata tertib",
            r"peraturan",
        ],
        "SOP": [
            r"SOP",
            r"standard\s+operating",
            r"prosedur",
            r"\balur\b",  # word-boundary: "alur" (workflow) alone, not inside "jalur" (admission pathway)
            r"procedure",
        ],
        "Form": [
            r"\bform\b",  # word-boundary: bare "form", not inside "informasi"/"reformasi"
            r"formulir",
            r"template",
            r"format",
            r"borang",
        ],
        "Brosur SPMB": [
            r"brosur",
            r"SPMB",
            r"seleksi",
            r"penerimaan\s+mahasiswa",
            r"admisi",
        ],
        "FAQ": [
            r"FAQ",
            r"frequently\s+asked",
            r"pertanyaan\s+umum",
            r"tanya\s+jawab",
        ],
    }

    # Explicit-override-only category: admins may select "Regulasi" when
    # uploading, but it is intentionally excluded from TYPE_PATTERNS so
    # automatic classification (sync worker, unattended uploads) doesn't
    # start guessing it — "tata tertib"/"peraturan" keywords already route
    # to "Pedoman" above and changing that would alter existing behavior.
    ALLOWED_TYPES = frozenset(TYPE_PATTERNS.keys()) | {"Regulasi"}

    # Real institutional titles are frequently a *combination* of category words
    # (e.g. "PEDOMAN SELEKSI PENERIMAAN MAHASISWA BARU (SPMB)..." matches both
    # "Pedoman" and "Brosur SPMB"). Highest-match-count scoring let generic
    # boilerplate phrasing ("penerimaan mahasiswa", "seleksi", "SPMB" — present
    # in nearly every admission-related title) numerically outweigh the single,
    # more specific "pedoman" keyword that actually identifies the document type.
    # Priority order instead: return the first category (in this order) with any
    # match at all, most-specific/least-ambiguous first, broadest catch-all last.
    PRIORITY_ORDER = ["Pedoman", "SOP", "Form", "FAQ", "Pengumuman", "Brosur SPMB"]

    @staticmethod
    def classify(filename: str, title: str = "", content_preview: str = "") -> str:
        """Classify document based on filename, title, and content preview."""
        combined = f"{filename} {title} {content_preview}".lower()

        for doc_type in DocumentClassifier.PRIORITY_ORDER:
            patterns = DocumentClassifier.TYPE_PATTERNS[doc_type]
            if any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns):
                return doc_type

        # Fallback based on extension
        if filename.lower().endswith(".pdf"):
            return "Pedoman"
        elif filename.lower().endswith(".docx"):
            return "Form"

        return "Pedoman"  # Default
