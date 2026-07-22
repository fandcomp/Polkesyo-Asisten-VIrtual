"""DocumentClassifierAgent (CLAUDE.md §11A.3) — wraps DocumentClassifier.classify.

`review_tier` is a derived, non-persisted value (decision #2 in CLAUDE.md §11A.3) — a pure
function of the existing 7-category `document_type`, not a new column or a replacement taxonomy.
"""
from app.agents.base_agent import BaseAgent
from app.services.document_classifier import DocumentClassifier

# Regulasi/Pedoman/SOP/Brosur SPMB require admin review before activation (CLAUDE.md §21.4).
# Pengumuman/FAQ are eligible for a lighter-touch review pass. Form needs field-mapping (CLAUDE.md
# §21.4's "Form must be mapped to activity/field/filler/usage requirements").
_REVIEW_TIER_BY_TYPE = {
    "Pengumuman": "auto_eligible",
    "FAQ": "auto_eligible",
    "Form": "needs_field_mapping",
    "Regulasi": "needs_review",
    "Pedoman": "needs_review",
    "SOP": "needs_review",
    "Brosur SPMB": "needs_review",
}


def get_review_tier(document_type: str) -> str:
    """Pure function: document_type -> review_tier. Never persisted (CLAUDE.md §11A.3)."""
    return _REVIEW_TIER_BY_TYPE.get(document_type, "needs_review")


class DocumentClassifierAgent(BaseAgent):
    name = "DocumentClassifierAgent"

    async def _run(self, input_data: dict) -> dict:
        filename: str = input_data.get("filename", "")
        title: str = input_data.get("title", "")
        content_preview: str = input_data.get("content_preview", "")

        document_type = DocumentClassifier.classify(filename, title, content_preview)
        review_tier = get_review_tier(document_type)

        return {
            "document_type": document_type,
            "review_tier": review_tier,
            "needs_admin_review": review_tier != "auto_eligible",
        }
