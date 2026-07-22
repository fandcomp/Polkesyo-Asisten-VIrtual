"""Text normalization for ACIF analysis."""
import re
import unicodedata

# Cyrillic/Greek characters visually indistinguishable from Latin letters (found live: a gold-QA
# test using Cyrillic п "п" in place of Latin "o" scored 0.0 risk signals and sailed through
# Gate 1 as "low risk" — unicodedata.normalize('NFKD', ...) does NOT fold these, since they are
# genuinely distinct code points, not combining-character variants of the same letter). Mapped to
# their Latin lookalike before phrase matching so a homoglyph-substituted injection phrase still
# matches RiskSignals' plain-ASCII phrase lists. Not exhaustive — covers the confusable letters
# that actually appear in ASCII injection phrases (ignore, admin, system, prompt, etc.).
_HOMOGLYPH_TO_LATIN = str.maketrans({
    # Cyrillic
    "а": "a", "А": "a", "е": "e", "Е": "e", "о": "o", "О": "o", "р": "p", "Р": "p",
    "с": "c", "С": "c", "у": "y", "У": "y", "х": "x", "Х": "x", "і": "i", "І": "i",
    "ѕ": "s", "Ѕ": "s", "ј": "j", "Ј": "j", "п": "n", "П": "n", "к": "k", "К": "k",
    "м": "m", "М": "m", "н": "h", "Н": "h", "в": "b", "В": "b", "т": "t", "Т": "t",
    # Greek
    "α": "a", "Α": "a", "ο": "o", "Ο": "o", "ρ": "p", "Ρ": "p", "ι": "i", "Ι": "i",
    "υ": "y", "Υ": "y", "τ": "t", "Τ": "t", "ν": "v", "Ν": "n",
})


class TextNormalizer:
    """Normalize text for security analysis."""

    @staticmethod
    def normalize(text: str) -> str:
        """Normalize text for analysis — strip zero-width chars, fold homoglyphs, normalize unicode."""
        # Remove zero-width characters (ZWJ, ZWSP, etc)
        text = re.sub(r'[​‌‍‎‏﻿]', '', text)

        # Fold Cyrillic/Greek homoglyphs to their Latin lookalikes before anything else, so
        # phrase matching below isn't defeated by single-character substitution.
        text = text.translate(_HOMOGLYPH_TO_LATIN)

        # Normalize unicode (decompose combined chars)
        text = unicodedata.normalize('NFKD', text)

        # Convert to lowercase for pattern matching
        text = text.lower()

        return text

    @staticmethod
    def extract_encoded_patterns(text: str) -> list[str]:
        """Try to detect base64 or hex encoded strings."""
        patterns = []
        
        # Detect potential base64 (4+ chars of base64 alphabet)
        if re.search(r'[A-Za-z0-9+/]{32,}={0,2}', text):
            patterns.append('potential_base64')
        
        # Detect hex strings (20+ hex chars)
        if re.search(r'[0-9a-f]{20,}', text.lower()):
            patterns.append('potential_hex')
        
        return patterns
