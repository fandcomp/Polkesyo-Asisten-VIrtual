"""VisionFormConversionAgent (structure-aware document extraction plan) — runs on
`form_vision` zone pages produced by DocumentStructureAgent: raster/scanned pages with no
selectable text (verified real example: page 26's FORMULIR PEMERIKSAAN KESEHATAN).

Reuses `ImageExtractor.extract_images_from_pdf` (already extracts the raster image + computes
a hash for the existing visual-chunk review pipeline) but calls the new
`VisionDescriptionService.describe_image_as_structured_table` instead of the prose-only vision
method, then renders the structured result into a `.docx` with a real Word table via the
shared `docx_builder` — same as `FormExtractionAgent`, this is never chunked/indexed and stays
`pending_review` until an admin approves it (CLAUDE.md §4.7/§21.6/§38).
"""
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.agents.base_agent import BaseAgent
from app.agents.form_extraction_agent import _slugify_title
from app.core.config import settings
from app.db.models import Document, DocumentFormExtract
from app.services.ingestion.docx_builder import build_form_docx
from app.services.ingestion.image_extractor import ImageExtractor
from app.services.ingestion.vision_description_service import (
    VisionDescriptionError,
    VisionDescriptionService,
)

logger = logging.getLogger(__name__)


class VisionFormConversionAgent(BaseAgent):
    name = "VisionFormConversionAgent"

    async def _run(self, input_data: dict) -> dict:
        db = input_data.get("db")
        document_id = input_data["document_id"]
        document_version_id = input_data["document_version_id"]
        filepath: str = input_data["filepath"]
        page_start: int = input_data["page_start"]
        page_end: int = input_data["page_end"]
        zone_title: str = input_data.get("zone_title") or "Formulir (Hasil Pindai)"

        try:
            extractor = ImageExtractor()
        except ImportError:
            logger.warning("PyMuPDF not available — skipping vision form conversion")
            return {"forms": [], "error": "PyMuPDF not available"}

        output_dir = str(Path(settings.processed_document_storage_path) / str(document_id) / "vision_forms")
        extracted_images = await extractor.extract_images_from_pdf(filepath, output_dir)
        zone_images = [
            img for img in extracted_images
            if page_start <= (img.get("page_number") or -1) <= page_end
        ]
        if not zone_images:
            return {"forms": []}

        all_fields: list[tuple[str, str]] = []
        all_tables: list[list[list[str]]] = []
        needs_admin_attention = False

        for image_meta in sorted(zone_images, key=lambda i: (i.get("page_number", 0), i.get("image_index", 0))):
            try:
                structured = await VisionDescriptionService.describe_image_as_structured_table(
                    image_meta["image_path"]
                )
            except VisionDescriptionError as exc:
                logger.warning(f"Structured-table vision failed for page {image_meta.get('page_number')}: {exc}")
                needs_admin_attention = True
                continue

            if structured.get("needs_admin_attention"):
                needs_admin_attention = True

            for field in structured.get("fields") or []:
                if isinstance(field, dict):
                    all_fields.append((str(field.get("label", "")), str(field.get("value", ""))))

            rows = structured.get("rows") or []
            if rows:
                all_tables.append([[str(cell) for cell in row] for row in rows])

        if not all_fields and not all_tables:
            # Nothing usable came back from any page in the zone — still flag for admin
            # rather than silently producing an empty document.
            return {"forms": [], "error": "No structured content extracted"}

        document_title = "Dokumen"
        if db is not None:
            try:
                document_title = (
                    await db.execute(select(Document.title).where(Document.id == document_id))
                ).scalar_one_or_none() or document_title
            except Exception as exc:
                logger.warning(f"Could not look up document title for {document_id}: {exc}")

        output_dir_docx = Path(settings.processed_document_storage_path) / str(document_id) / "forms"
        output_dir_docx.mkdir(parents=True, exist_ok=True)
        slug = _slugify_title(document_title)
        output_path = str(output_dir_docx / f"{slug}_vision_p{page_start:04d}_{uuid4().hex[:8]}.docx")
        build_form_docx(zone_title, all_fields, all_tables, output_path)

        if db is not None:
            try:
                record = DocumentFormExtract(
                    document_id=document_id,
                    document_version_id=document_version_id,
                    zone_type="form_vision",
                    form_title=zone_title,
                    source_page_start=page_start,
                    source_page_end=page_end,
                    extraction_method="vision",
                    docx_artifact_path=output_path,
                    status="pending_review",
                    admin_notes=(
                        "Hasil ekstraksi visual perlu perhatian admin — sebagian tidak "
                        "sepenuhnya terstruktur/terbaca." if needs_admin_attention else None
                    ),
                )
                db.add(record)
                await db.commit()
            except Exception as exc:
                logger.error(f"Failed to persist document_form_extracts for '{zone_title}': {exc}")

        return {
            "forms": [{
                "title": zone_title,
                "start_page": page_start,
                "end_page": page_end,
                "docx_artifact_path": output_path,
                "needs_admin_attention": needs_admin_attention,
            }]
        }
