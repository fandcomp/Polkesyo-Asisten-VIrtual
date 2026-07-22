"""Integration test: full IngestionService.ingest_document() run against a small synthetic
PDF (built at test time via PyMuPDF, not committed — the real ground-truth document is a live
production file with real SK numbers) that reproduces the divider-page template in miniature:
one body page, one divider page, and one form_text page.

Confirms the critical no-regression guarantee from the approved plan: zero `DocumentChunk`
rows are created for the form-zone page, and exactly one `DocumentFormExtract` row
(`pending_review`) is created instead. Follows this test suite's existing convention (see
tests/integration/test_flexible_questions_pipeline.py) of mocking the DB session boundary with
AsyncMock/MagicMock rather than a real database.
"""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models import ChunkSummary, DocumentChunk, DocumentFormExtract
from app.services.ingestion_service import IngestionService

fitz = pytest.importorskip("fitz", reason="PyMuPDF required to build the synthetic test PDF")


def _build_synthetic_pedoman_pdf(path: Path) -> None:
    """One body page, one divider page ('DOKUMEN PENDAFTARAN'), one form_text page ('SURAT
    PERNYATAAN' with numbered fields) — the minimal shape needed to exercise
    DocumentStructureAgent's divider detection end to end."""
    doc = fitz.open()

    page1 = doc.new_page()
    for i, line in enumerate([
        "A. Latar Belakang",
        "Poltekkes Kemenkes Yogyakarta menyelenggarakan pendaftaran mahasiswa baru",
        "melalui beberapa jalur setiap tahun akademik untuk berbagai program studi.",
    ]):
        page1.insert_text((72, 72 + i * 20), line, fontsize=11)

    page2 = doc.new_page()
    page2.insert_text((72, 72), "DOKUMEN PENDAFTARAN", fontsize=11)

    page3 = doc.new_page()
    for i, line in enumerate([
        "SURAT PERNYATAAN",
        "1. Nama: ....",
        "2. NIK: ....",
    ]):
        page3.insert_text((72, 72 + i * 20), line, fontsize=11)

    doc.save(str(path))
    doc.close()


class _CountResult:
    def scalar(self):
        return 0


class _DocumentTypeResult:
    def scalar_one_or_none(self):
        return "Pedoman"


@pytest.mark.asyncio
class TestDocumentStructureIngestionFlow:
    async def test_form_zone_page_excluded_from_chunks_and_creates_form_extract(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "synthetic_pedoman.pdf"
            _build_synthetic_pedoman_pdf(pdf_path)

            added_objects: list = []
            db = MagicMock()
            db.add = MagicMock(side_effect=added_objects.append)
            db.commit = AsyncMock()
            db.flush = AsyncMock()
            db.execute = AsyncMock(side_effect=[_CountResult(), _DocumentTypeResult()])

            with patch(
                "app.agents.form_extraction_agent.settings.processed_document_storage_path", tmp
            ), patch(
                "app.services.chunk_summary_service.settings.openrouter_api_key", ""
            ):
                result = await IngestionService.ingest_document(
                    db, document_version_id="ver-1", document_id="doc-1", filepath=str(pdf_path)
                )

            assert result.get("status") == "completed", result

            chunks_added = [o for o in added_objects if isinstance(o, DocumentChunk)]
            summaries_added = [o for o in added_objects if isinstance(o, ChunkSummary)]
            forms_added = [o for o in added_objects if isinstance(o, DocumentFormExtract)]

            # The form_text zone (page 3) must never become a DocumentChunk.
            assert len(chunks_added) >= 1
            assert len(summaries_added) == len(chunks_added)
            for chunk in chunks_added:
                assert "SURAT PERNYATAAN" not in (chunk.original_text or "")

            # Exactly one form extract, pending admin review, pointing at page 3.
            assert len(forms_added) == 1
            form = forms_added[0]
            assert form.status == "pending_review"
            assert form.zone_type == "form_text"
            assert form.source_page_start == 3
            assert form.source_page_end == 3
            # Must stay inside both TemporaryDirectory contexts — they delete their
            # directories (and everything written into them) on __exit__.
            assert Path(form.docx_artifact_path).is_file()

            assert result["form_extracts_created"] == 1
