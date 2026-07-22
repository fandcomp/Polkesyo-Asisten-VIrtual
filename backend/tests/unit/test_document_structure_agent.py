"""Unit tests for DocumentStructureAgent (structure-aware document extraction plan).

Uses plain-text/synthetic page fixtures built from the real headings verified by hand-
inspecting the production Pedoman PDF on the VPS (see the approved plan) — not a committed
copy of the actual document, which is a live production file with real SK numbers.
"""
import pytest

from app.agents.document_structure_agent import DocumentStructureAgent


def _page(page: int, text: str, image_count: int = 0, table_count: int = 0) -> dict:
    return {"page": page, "text": text, "image_count": image_count, "table_count": table_count}


# A miniature version of the verified real template: cover -> SK preamble -> daftar isi ->
# lettered body -> DOKUMEN PENDAFTARAN divider -> a text form -> DOKUMEN UJI KESEHATAN divider
# -> a raster/vision form page + a blank continuation page + a text-native form page.
_TEMPLATE_PAGES = [
    _page(1, "SPMB PRESTASI TAHUN AKADEMIK 2026/2027"),
    _page(2, "KEPUTUSAN DIREKTUR\nMENIMBANG: bahwa perlu...\nMENETAPKAN: ..."),
    _page(3, "DAFTAR ISI"),
    _page(4, "A. Latar Belakang\nPoltekkes Kemenkes Yogyakarta menyelenggarakan..."),
    _page(5, "DOKUMEN PENDAFTARAN"),
    _page(6, "SURAT PERNYATAAN\n1. Nama: ....\n2. NIK: ...."),
    _page(7, "DOKUMEN UJI KESEHATAN"),
    _page(8, "", image_count=2),  # FORMULIR PEMERIKSAAN KESEHATAN — raster, no selectable text
    _page(9, ""),  # blank signature continuation, no images
    _page(10, "HASIL PEMERIKSAAN PSIKOLOGIS\n| No | Nama | Hasil |\n| --- | --- | --- |\n| 1 | A | Lulus |"),
]


@pytest.mark.asyncio
class TestDocumentStructureAgentZoneDetection:
    async def test_detects_decision_letter_zone(self):
        result = await DocumentStructureAgent().execute(
            {"document_type": "Pedoman", "pages": _TEMPLATE_PAGES}
        )
        zones = result.output["zones"]
        decision_zones = [z for z in zones if z["zone_type"] == "decision_letter"]
        assert len(decision_zones) == 1
        assert decision_zones[0]["start_page"] == 2
        assert decision_zones[0]["end_page"] == 2

    async def test_detects_body_zone_up_to_first_divider(self):
        result = await DocumentStructureAgent().execute(
            {"document_type": "Pedoman", "pages": _TEMPLATE_PAGES}
        )
        zones = result.output["zones"]
        body_zones = [z for z in zones if z["zone_type"] == "body"]
        assert len(body_zones) == 1
        assert body_zones[0]["start_page"] == 1
        assert body_zones[0]["end_page"] == 4  # page before the first divider (page 5)

    async def test_detects_form_text_zone_with_divider_title(self):
        result = await DocumentStructureAgent().execute(
            {"document_type": "Pedoman", "pages": _TEMPLATE_PAGES}
        )
        zones = result.output["zones"]
        pendaftaran_zones = [z for z in zones if z.get("title") == "DOKUMEN PENDAFTARAN"]
        assert len(pendaftaran_zones) == 1
        assert pendaftaran_zones[0]["zone_type"] == "form_text"
        assert pendaftaran_zones[0]["start_page"] == 6
        assert pendaftaran_zones[0]["end_page"] == 6

    async def test_splits_mixed_divider_region_into_vision_then_text_subzones(self):
        """The DOKUMEN UJI KESEHATAN region mixes a vision-only sub-form (pages 8-9) with a
        text-native sub-form (page 10) — verified real structure — so it must produce TWO
        zones under the same divider title, not one."""
        result = await DocumentStructureAgent().execute(
            {"document_type": "Pedoman", "pages": _TEMPLATE_PAGES}
        )
        zones = result.output["zones"]
        uji_kesehatan_zones = [z for z in zones if z.get("title") == "DOKUMEN UJI KESEHATAN"]
        assert len(uji_kesehatan_zones) == 2

        vision_zone, text_zone = uji_kesehatan_zones
        assert vision_zone["zone_type"] == "form_vision"
        assert vision_zone["start_page"] == 8
        assert vision_zone["end_page"] == 9  # blank page 9 inherits the vision run's type

        assert text_zone["zone_type"] == "form_text"
        assert text_zone["start_page"] == 10
        assert text_zone["end_page"] == 10

    async def test_unsupported_document_type_produces_zero_zones(self):
        result = await DocumentStructureAgent().execute(
            {"document_type": "SOP", "pages": _TEMPLATE_PAGES}
        )
        assert result.output["zones"] == []

    async def test_no_divider_pages_falls_back_to_zero_zones(self):
        """A Pedoman document that doesn't match the divider-page template must produce zero
        zones — the caller then falls through to today's single flat-body ingestion path."""
        plain_pages = [
            _page(1, "Cover"),
            _page(2, "A. Pendahuluan\nIsi narasi biasa tanpa halaman pembatas apa pun."),
            _page(3, "B. Penutup\nDemikian pedoman ini dibuat."),
        ]
        result = await DocumentStructureAgent().execute(
            {"document_type": "Pedoman", "pages": plain_pages}
        )
        assert result.output["zones"] == []

    async def test_empty_pages_list_produces_zero_zones(self):
        result = await DocumentStructureAgent().execute({"document_type": "Pedoman", "pages": []})
        assert result.output["zones"] == []
