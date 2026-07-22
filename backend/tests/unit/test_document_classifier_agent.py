"""Unit tests for DocumentClassifierAgent's derived review_tier (CLAUDE.md §11A.3)."""
import pytest

from app.agents.document_classifier_agent import DocumentClassifierAgent, get_review_tier


class TestReviewTier:
    def test_pengumuman_is_auto_eligible(self):
        assert get_review_tier("Pengumuman") == "auto_eligible"

    def test_regulasi_needs_review(self):
        assert get_review_tier("Regulasi") == "needs_review"

    def test_pedoman_needs_review(self):
        assert get_review_tier("Pedoman") == "needs_review"

    def test_form_needs_field_mapping(self):
        assert get_review_tier("Form") == "needs_field_mapping"

    def test_unknown_type_defaults_to_needs_review(self):
        assert get_review_tier("SomethingUnexpected") == "needs_review"


@pytest.mark.asyncio
class TestDocumentClassifierAgent:
    async def test_classifies_and_derives_tier_together(self):
        result = await DocumentClassifierAgent().execute({
            "filename": "pengumuman_hasil_seleksi.pdf",
            "title": "Pengumuman Hasil Seleksi Tahap 1",
        })
        assert result.output["document_type"] == "Pengumuman"
        assert result.output["review_tier"] == "auto_eligible"
        assert result.output["needs_admin_review"] is False

    async def test_form_document_needs_admin_review_flag_true(self):
        result = await DocumentClassifierAgent().execute({
            "filename": "formulir_pernyataan.pdf",
            "title": "Formulir Surat Pernyataan",
        })
        assert result.output["document_type"] == "Form"
        assert result.output["needs_admin_review"] is True
