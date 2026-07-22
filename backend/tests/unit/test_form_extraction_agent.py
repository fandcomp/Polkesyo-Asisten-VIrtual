"""Unit tests for FormExtractionAgent's boundary heuristic (structure-aware document
extraction plan).

Synthetic multi-page text reproducing the verified Daftar Ulang page-continuation case:
numbered fields spanning p.31->32 = same form; p.30->31 = different forms (new heading).
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.agents.form_extraction_agent import FormExtractionAgent

_PAGE_30 = {
    "page": 30,
    "text": "FORMULIR CHECKLIST DAFTAR ULANG\n1. Ijazah\n2. Transkrip Nilai\n3. Kartu Tanda Penduduk",
}
_PAGE_31 = {
    "page": 31,
    "text": "SURAT PERNYATAAN KESANGGUPAN\n1. Nama: ..........\n2. Alamat: ..........",
}
_PAGE_32 = {
    "page": 32,
    "text": "3. Nomor telepon: ..........\n4. Tanda tangan: ..........",
}


@pytest.mark.asyncio
class TestSameFormDetection:
    async def test_new_heading_starts_a_new_form(self):
        """p.30 -> p.31: page 31 opens with a new 'SURAT PERNYATAAN' heading, so it must be
        treated as a different form even though both pages have numbered fields."""
        same = await FormExtractionAgent._same_form(_PAGE_30, _PAGE_31)
        assert same is False

    async def test_sequential_numbering_continues_the_same_form(self):
        """p.31 -> p.32: page 32 has no new heading and its first numbered field (3) is
        exactly page 31's last numbered field (2) + 1 -> same form continuing."""
        same = await FormExtractionAgent._same_form(_PAGE_31, _PAGE_32)
        assert same is True

    async def test_restarted_numbering_without_heading_is_ambiguous_and_defaults_to_new_form(self):
        """No heading match and numbering restarts (not sequential) -> ambiguous. With no
        OpenRouter key configured (test environment), the tie-break defaults to 'new form'
        (the safer assumption — never silently merges two distinct forms)."""
        prev = {"page": 40, "text": "1. Item satu\n2. Item dua"}
        curr = {"page": 41, "text": "1. Item lain\n2. Item lain lagi"}
        with patch("app.agents.form_extraction_agent.settings.openrouter_api_key", ""):
            same = await FormExtractionAgent._same_form(prev, curr)
        assert same is False


class TestExtractTitle:
    def test_extracts_heading_line(self):
        title = FormExtractionAgent._extract_title([_PAGE_31])
        assert title == "SURAT PERNYATAAN KESANGGUPAN"

    def test_returns_none_when_no_heading_present(self):
        title = FormExtractionAgent._extract_title([{"page": 1, "text": "Isi tanpa judul formulir"}])
        assert title is None


class TestExtractFieldsAndTables:
    def test_extracts_label_value_fields(self):
        # Verbatim requirement: the numbered-item prefix stays part of the label exactly as
        # written in the source ("1. Nama", not "Nama") — no reformatting.
        fields, tables, items = FormExtractionAgent._extract_fields_and_tables([_PAGE_31])
        assert ("1. Nama", "..........") in fields
        assert ("2. Alamat", "..........") in fields
        assert tables == []
        assert items == [
            ("field", ("SURAT PERNYATAAN KESANGGUPAN", "")),
            ("field", ("1. Nama", "..........")),
            ("field", ("2. Alamat", "..........")),
        ]

    def test_extracts_bare_lines_as_fields_with_empty_value(self):
        fields, _, _ = FormExtractionAgent._extract_fields_and_tables([_PAGE_30])
        labels = [f[0] for f in fields]
        assert "2. Transkrip Nilai" in labels or "Transkrip Nilai" in " ".join(labels)

    def test_extracts_markdown_table_rows(self):
        page = {
            "page": 1,
            "text": "| No | Nama | Status |\n| --- | --- | --- |\n| 1 | Budi | Lulus |",
        }
        fields, tables, items = FormExtractionAgent._extract_fields_and_tables([page])
        assert tables == [[["No", "Nama", "Status"], ["1", "Budi", "Lulus"]]]
        assert items == [("table", [["No", "Nama", "Status"], ["1", "Budi", "Lulus"]])]

    def test_interleaves_fields_and_tables_in_original_order(self):
        """2026-07-22 fix: fields/tables used to render as two separate blocks (all fields,
        then all tables), silently reordering content relative to the source document. `items`
        must preserve the real as-they-appear order — table between two fields here."""
        page = {
            "page": 1,
            "text": "Nama: Budi\n| No | Status |\n| --- | --- |\n| 1 | Lulus |\nAlamat: Jakarta",
        }
        _, _, items = FormExtractionAgent._extract_fields_and_tables([page])
        assert [kind for kind, _ in items] == ["field", "table", "field"]
        assert items[0] == ("field", ("Nama", "Budi"))
        assert items[2] == ("field", ("Alamat", "Jakarta"))

    def test_bare_page_number_lines_are_excluded(self):
        """2026-07-22 fix: PyMuPDF extracts a PDF page's printed footer/header page number
        alongside its body text (e.g. a lone "18") — verified real leakage into extracted
        form output; must never appear as a spurious field."""
        page = {"page": 18, "text": "SURAT PERNYATAAN\n18\nNama\n18\nAlamat"}
        fields, _, _ = FormExtractionAgent._extract_fields_and_tables([page])
        labels = [f[0] for f in fields]
        assert "18" not in labels
        assert labels == ["SURAT PERNYATAAN", "Nama", "Alamat"]

    def test_table_page_marker_is_excluded(self):
        """TextExtractor's synthetic '[Tabel halaman N]' marker (text_extractor.py) must not
        leak into a verbatim form reproduction as a spurious field."""
        page = {"page": 24, "text": "Nama\n[Tabel halaman 24]\nAlamat"}
        fields, _, _ = FormExtractionAgent._extract_fields_and_tables([page])
        labels = [f[0] for f in fields]
        assert "[Tabel halaman 24]" not in labels
        assert labels == ["Nama", "Alamat"]

    def test_tcpdf_generator_watermark_is_excluded(self):
        """Verified real leakage: the source PDF's own 'Powered by TCPDF' generator
        watermark line, extracted the same way page numbers are."""
        page = {"page": 33, "text": "Nama\nPowered by TCPDF (www.tcpdf.org)\nAlamat"}
        fields, _, _ = FormExtractionAgent._extract_fields_and_tables([page])
        labels = [f[0] for f in fields]
        assert not any("tcpdf" in label.lower() for label in labels)
        assert labels == ["Nama", "Alamat"]


class TestSlugifyTitle:
    def test_slugifies_indonesian_title_for_filename_use(self):
        from app.agents.form_extraction_agent import _slugify_title

        slug = _slugify_title("Pedoman SPMB Mandiri Reguler SMA Poltekkes Kemenkes Yogyakarta TA 2026-2027")
        assert " " not in slug
        assert "/" not in slug
        assert slug.startswith("Pedoman_SPMB")

    def test_empty_title_falls_back_to_generic_name(self):
        from app.agents.form_extraction_agent import _slugify_title

        assert _slugify_title("   ") == "dokumen"


@pytest.mark.asyncio
class TestFormExtractionAgentRun:
    async def test_groups_pages_into_forms_and_writes_docx(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "app.agents.form_extraction_agent.settings.processed_document_storage_path", tmp
        ):
            result = await FormExtractionAgent().execute({
                "document_id": "doc-1",
                "document_version_id": "ver-1",
                "pages": [_PAGE_30, _PAGE_31, _PAGE_32],
                "zone_title": "DOKUMEN DAFTAR ULANG",
            })

            assert result.status == "success"
            forms = result.output["forms"]
            # p.30 alone (different form from p.31), p.31+p.32 merged (sequential numbering)
            assert len(forms) == 2
            assert forms[0]["start_page"] == 30 and forms[0]["end_page"] == 30
            assert forms[1]["start_page"] == 31 and forms[1]["end_page"] == 32
            for form in forms:
                # Assertions must stay inside the TemporaryDirectory context — it deletes the
                # directory (and every file written into it) on __exit__.
                assert Path(form["docx_artifact_path"]).is_file()

    async def test_empty_pages_produces_no_forms(self):
        result = await FormExtractionAgent().execute({
            "document_id": "doc-1",
            "document_version_id": "ver-1",
            "pages": [],
        })
        assert result.status == "success"
        assert result.output["forms"] == []
