"""Orchestrate document ingestion: extract → chunk → summarize → store."""
import logging
from pathlib import Path
from uuid import uuid4
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.models import Document, DocumentChunk, ChunkSummary
from app.services.id_generation import chunk_id_for
from app.services.text_extractor import TextExtractor
from app.services.chunking_service import ChunkingService
from app.services.chunk_summary_service import ChunkSummaryService
from app.services.ingestion.image_extractor import ImageExtractor
from app.services.ingestion.visual_chunk_builder import VisualChunkBuilder
from app.services.ingestion.visual_data_consistency_checker import VisualDataConsistencyChecker
from app.services.ingestion import zone_patterns

logger = logging.getLogger(__name__)


class IngestionService:
    """Orchestrate full ingestion pipeline."""

    @staticmethod
    async def ingest_document(
        db: AsyncSession,
        document_version_id: str,
        document_id: str,
        filepath: str,
        include_visual_chunks: bool = True,
    ) -> dict:
        """Full ingestion pipeline for a document.

        `include_visual_chunks=False` skips Step 0 (image/table-screenshot extraction) —
        used when re-chunking an already-ingested document (e.g. after a chunking bug fix)
        where visual chunks are unaffected and re-running them would create duplicate
        approved visual chunks for unchanged images (no dedup-by-image_hash exists)."""
        result = {
            "document_version_id": document_version_id,
            "chunks_created": 0,
            "visual_chunks_created": 0,
            "form_extracts_created": 0,
            "errors": [],
        }

        try:
            # Guard: re-running ingestion for a version must not duplicate chunks
            existing_stmt = select(func.count(DocumentChunk.id)).where(
                DocumentChunk.document_version_id == document_version_id
            )
            existing = (await db.execute(existing_stmt)).scalar() or 0
            if existing:
                result["error"] = (
                    f"Version already has {existing} chunk(s) — ingestion skipped"
                )
                return result

            # Step 0: Extract embedded images (PDF only) and build visual chunks
            # for admin review — independent of text extraction below, so a
            # scanned/image-heavy PDF still gets reviewable content even if
            # text extraction finds little or nothing.
            if include_visual_chunks and filepath.lower().endswith(".pdf"):
                await IngestionService._ingest_visual_chunks(
                    db, document_version_id, document_id, filepath, result
                )

            # Step 0.5: Structure-aware zone detection (PDF-only, Pedoman-template documents
            # only — see zone_patterns.SUPPORTED_DOCUMENT_TYPES). Produces form_text/
            # form_vision zones whose pages must be excluded from flat chunking below and
            # instead routed to FormExtractionAgent/VisionFormConversionAgent. Any document
            # that doesn't match the template (wrong type, or a Pedoman doc with no divider
            # pages) yields zero zones -> the exact pre-existing flat-text path below runs
            # unchanged. Never blocks ingestion: a failure here just means zero zones.
            form_zones: list[dict] = []
            pages: list[dict] = []
            if filepath.lower().endswith(".pdf"):
                try:
                    pages, form_zones = await IngestionService._detect_form_zones(
                        db, document_id, filepath
                    )
                except Exception as e:
                    logger.warning(f"Zone detection failed, falling back to flat ingestion: {e}")
                    pages, form_zones = [], []

            # Step 1: Extract text — excluding any page claimed by a form_text/form_vision
            # zone above, so those pages are never chunked/summarized/indexed (the user's
            # "tidak perlu dijadikan chunk" requirement). When no form zones were detected
            # (the overwhelmingly common case today), this is byte-for-byte the original
            # extract_from_file() call.
            excluded_pages = {
                p for zone in form_zones for p in range(zone["start_page"], zone["end_page"] + 1)
            }
            if pages and excluded_pages:
                remaining = "\n".join(p["text"] for p in pages if p["page"] not in excluded_pages)
                text = TextExtractor._clean_boilerplate(remaining)
            else:
                text = await TextExtractor.extract_from_file(filepath)
            # A document made entirely of form-zone pages (no body/decision_letter text left
            # over) must still dispatch its form zones below rather than aborting ingestion —
            # only bail here if there's neither flat text NOR any form zone to route instead.
            if not text and not form_zones:
                result["error"] = "Failed to extract text"
                return result

            # Step 2: Chunk text — structure-aware (section headings, numbered items,
            # paragraphs, then sentences; never mid-sentence). Replaces the old fixed-
            # token-count chunk_text(), which ignored document structure entirely.
            chunks = ChunkingService.chunk_text_structured(text) if text else []
            if not chunks and not form_zones:
                result["error"] = "No chunks generated"
                return result

            # Step 3: Create chunk records and generate summaries
            for idx, chunk_data in enumerate(chunks):
                try:
                    chunk_text = chunk_data["text"]
                    chunk_id = f"doc_{document_id}_{idx}"
                    token_count = ChunkingService.get_chunk_token_count(chunk_text)

                    # Create chunk record
                    chunk = DocumentChunk(
                        id=chunk_id_for(document_version_id, idx, chunk_kind="text"),
                        chunk_id=chunk_id,
                        document_id=document_id,
                        document_version_id=document_version_id,
                        chunk_index=idx,
                        section=chunk_data.get("section"),
                        original_text=chunk_text,
                        token_count=token_count,
                        status="created",
                    )
                    db.add(chunk)
                    await db.flush()

                    # Generate summary draft. Table-containing chunks get a larger output
                    # budget — the summary prompt now requires enumerating every table row
                    # verbatim instead of paraphrasing, which needs materially more tokens
                    # than a normal one-paragraph summary to avoid being cut off mid-table.
                    summary_max_tokens = (
                        max(settings.chunk_summary_max_tokens, 1200)
                        if ChunkingService.contains_table(chunk_text)
                        else None
                    )
                    summary_text = await ChunkSummaryService.generate_summary(
                        chunk_text, max_tokens=summary_max_tokens
                    )

                    # Create summary record
                    summary = ChunkSummary(
                        id=uuid4(),
                        chunk_id=chunk.id,
                        llm_summary_draft=summary_text,
                        summary_status="draft",
                    )
                    db.add(summary)

                    result["chunks_created"] += 1

                except Exception as e:
                    await db.rollback()
                    result["errors"].append(f"Chunk {idx}: {str(e)}")

            # Commit all chunks and summaries
            await db.commit()

            # Step 3.5: Dispatch form_text/form_vision zones to FormExtractionAgent /
            # VisionFormConversionAgent. No-op when form_zones is empty (every non-Pedoman
            # document, and any Pedoman document without the divider-page template).
            if form_zones:
                await IngestionService._dispatch_form_zones(
                    db, document_id, document_version_id, filepath, pages, form_zones, result
                )

            # Step 4: Cross-check each visual chunk's extracted data against this
            # document's own text chunks (now that both exist) — flags factual
            # conflicts (a fee/date/number stated differently in each source) directly
            # into the visual chunk's existing risk_flags/uncertainty_notes fields, so
            # it surfaces in the admin review UI with zero frontend changes needed.
            # Never blocks ingestion: a failed check just means no flag gets added.
            for visual_chunk_id in result.get("visual_chunk_ids", []):
                try:
                    await IngestionService._check_visual_data_consistency(db, visual_chunk_id, document_id)
                except Exception as e:
                    logger.warning(f"Consistency check failed for visual chunk {visual_chunk_id}: {e}")

            result["status"] = "completed"

        except Exception as e:
            result["error"] = str(e)

        return result

    @staticmethod
    async def _ingest_visual_chunks(
        db: AsyncSession,
        document_version_id: str,
        document_id: str,
        filepath: str,
        result: dict,
    ) -> None:
        """Extract embedded images from a PDF, assess quality, generate vision
        descriptions, and store `pending_review` visual chunks. Mutates
        `result` in place; never raises — a failure here must not prevent the
        text-ingestion steps that follow from running."""
        try:
            extractor = ImageExtractor()
        except ImportError:
            logger.warning("PyMuPDF not available — skipping visual chunk extraction")
            return

        try:
            output_dir = str(Path(settings.processed_document_storage_path) / document_id / "images")
            extracted_images = await extractor.extract_images_from_pdf(filepath, output_dir)

            # Vector-drawn tables (lines + positioned text, not an embedded raster stream)
            # are invisible to extract_images_from_pdf above — screenshot them separately
            # via native table-structure detection so every table in the document gets a
            # reviewable image too, not just embedded pictures/logos/QR codes.
            try:
                table_screenshots = await extractor.extract_table_screenshots_from_pdf(filepath, output_dir)
                extracted_images.extend(table_screenshots)
            except Exception as e:
                logger.warning(f"Table screenshot extraction failed, continuing without it: {e}")

            if not extracted_images:
                return

            image_quality = {
                img["image_hash"]: await extractor.assess_image_quality(img["image_path"])
                for img in extracted_images
            }

            visual_chunks, visual_errors = await VisualChunkBuilder.create_visual_chunks(
                db, document_version_id, document_id, extracted_images, image_quality
            )
            result["visual_chunks_created"] = len(visual_chunks)
            result["visual_chunk_ids"] = [c["chunk_id"] for c in visual_chunks]
            result["errors"].extend(f"Visual: {e}" for e in visual_errors)

        except Exception as e:
            logger.error(f"Visual chunk extraction failed: {e}")
            result["errors"].append(f"Visual extraction failed: {e}")

    @staticmethod
    async def _detect_form_zones(
        db: AsyncSession,
        document_id: str,
        filepath: str,
    ) -> tuple[list[dict], list[dict]]:
        """Run DocumentStructureAgent over the page-indexed extraction and return
        `(pages, form_zones)` where `form_zones` is only the `form_text`/`form_vision` zones
        (decision_letter/body zones don't need to be excluded from anything — the existing
        flat-chunking path already handles them). Returns `([], [])` for any document whose
        type isn't in `zone_patterns.SUPPORTED_DOCUMENT_TYPES` or that has no divider pages —
        the caller then falls through to today's exact flat-ingestion behavior."""
        # Local import: DocumentStructureAgent lives in app.agents, which is a higher-level
        # package than app.services — importing it at module scope here would invert the
        # dependency direction the rest of this file follows (services don't import agents
        # at top level elsewhere in this codebase).
        from app.agents.document_structure_agent import DocumentStructureAgent

        doc_stmt = select(Document.document_type).where(Document.id == document_id)
        document_type = (await db.execute(doc_stmt)).scalar_one_or_none()
        if not document_type or document_type not in zone_patterns.SUPPORTED_DOCUMENT_TYPES:
            return [], []

        pages = await TextExtractor.extract_pages_from_pdf(filepath)
        if not pages:
            return [], []

        structure_result = await DocumentStructureAgent().execute(
            {"document_type": document_type, "pages": pages}, db=db, task_type="ingestion"
        )
        if structure_result.status != "success":
            return pages, []

        zones = (structure_result.output or {}).get("zones", [])
        form_zones = [z for z in zones if z["zone_type"] in ("form_text", "form_vision")]
        return pages, form_zones

    @staticmethod
    async def _dispatch_form_zones(
        db: AsyncSession,
        document_id: str,
        document_version_id: str,
        filepath: str,
        pages: list[dict],
        form_zones: list[dict],
        result: dict,
    ) -> None:
        """Route each form_text zone to FormExtractionAgent and each form_vision zone to
        VisionFormConversionAgent. Mutates `result` in place; never raises — one zone's
        failure must not prevent the rest of ingestion (or the remaining zones) from
        completing."""
        # Local imports for the same reason as _detect_form_zones above.
        from app.agents.form_extraction_agent import FormExtractionAgent
        from app.agents.vision_form_conversion_agent import VisionFormConversionAgent

        pages_by_num = {p["page"]: p for p in pages}

        for zone in form_zones:
            try:
                if zone["zone_type"] == "form_text":
                    zone_pages = [
                        pages_by_num[p]
                        for p in range(zone["start_page"], zone["end_page"] + 1)
                        if p in pages_by_num
                    ]
                    agent_result = await FormExtractionAgent().execute(
                        {
                            "db": db,
                            "document_id": document_id,
                            "document_version_id": document_version_id,
                            "pages": zone_pages,
                            "zone_title": zone.get("title"),
                        },
                        db=db,
                        task_type="ingestion",
                    )
                else:
                    agent_result = await VisionFormConversionAgent().execute(
                        {
                            "db": db,
                            "document_id": document_id,
                            "document_version_id": document_version_id,
                            "filepath": filepath,
                            "page_start": zone["start_page"],
                            "page_end": zone["end_page"],
                            "zone_title": zone.get("title"),
                        },
                        db=db,
                        task_type="ingestion",
                    )

                if agent_result.status == "success":
                    forms = (agent_result.output or {}).get("forms", [])
                    result["form_extracts_created"] += len(forms)
                else:
                    result["errors"].append(
                        f"Form zone {zone['start_page']}-{zone['end_page']}: {agent_result.error}"
                    )
            except Exception as e:
                result["errors"].append(
                    f"Form zone {zone['start_page']}-{zone['end_page']}: {e}"
                )

    @staticmethod
    async def _check_visual_data_consistency(
        db: AsyncSession, visual_chunk_id: str, document_id: str
    ) -> None:
        """Run VisualDataConsistencyChecker for one visual chunk against this document's
        text chunks, writing any detected conflict into the chunk's existing
        risk_flags/uncertainty_notes — reusing fields the admin review UI already
        renders (VisualChunkReviewCard.tsx), so no frontend change is needed for the
        reason to become visible."""
        chunk = await db.get(DocumentChunk, visual_chunk_id)
        if chunk is None:
            return

        check_result = await VisualDataConsistencyChecker.check_visual_chunk_against_document(
            db, chunk, document_id
        )
        if not check_result.get("conflict_detected"):
            return

        reason = check_result.get("reason") or "Konflik data terdeteksi antara gambar dan teks dokumen."
        risk_flags = list(chunk.risk_flags or [])
        if "data_conflict_detected" not in risk_flags:
            risk_flags.append("data_conflict_detected")
        chunk.risk_flags = risk_flags

        existing_notes = chunk.uncertainty_notes or ""
        conflict_note = f"⚠ Potensi konflik data (dibandingkan otomatis dengan teks dokumen): {reason}"
        chunk.uncertainty_notes = f"{existing_notes}\n{conflict_note}".strip() if existing_notes else conflict_note

        await db.commit()
