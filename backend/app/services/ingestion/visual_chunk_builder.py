"""Build visual chunks from extracted images."""
import logging
import os
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.core.config import settings
from app.db.models import DocumentChunk
from app.services.id_generation import chunk_id_for
from app.services.ingestion.vision_description_service import (
    VisionDescriptionService,
    VisionDescriptionError,
)

logger = logging.getLogger(__name__)


class VisualChunkBuilder:
    """Create and store visual chunks for admin review."""

    @staticmethod
    async def create_visual_chunks(
        db: AsyncSession,
        document_version_id: str,
        document_id: str,
        extracted_images: list[dict],
        image_quality: dict,
    ) -> tuple[list[dict], list[str]]:
        """Create visual chunks from extracted images.

        Returns:
            (created_chunks, errors)
        """

        created_chunks = []
        errors = []

        env_override = os.environ.get("VISION_EXTRACTION_ENABLED")
        vision_enabled = (
            env_override.lower() == "true" if env_override is not None
            else settings.vision_extraction_enabled
        )

        if not vision_enabled:
            logger.info("Vision extraction disabled")
            return created_chunks, []

        for image_meta in extracted_images:
            try:
                image_path = image_meta.get("image_path")
                page_num = image_meta.get("page_number")
                image_hash = image_meta.get("image_hash")

                quality = image_quality.get(image_hash, {})
                should_process, reason = await VisualChunkBuilder._should_process(quality)

                if not should_process:
                    logger.info(f"Skip image: {reason}")
                    continue

                # Generate vision description
                try:
                    vision_output = await VisionDescriptionService.generate_vision_description(image_path)
                except VisionDescriptionError as e:
                    logger.warning(f"Vision failed: {e}")
                    errors.append(f"Page {page_num}: {str(e)}")
                    continue

                # Create chunk data
                chunk_data = await VisionDescriptionService.create_visual_chunk_draft(
                    image_meta,
                    vision_output,
                    quality,
                )

                # Store in database
                chunk_id = str(uuid4())
                image_index = image_meta.get("image_index", 0)
                chunk = DocumentChunk(
                    id=chunk_id_for(document_version_id, image_index, chunk_kind="image"),
                    chunk_id=chunk_id,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    chunk_index=image_index,
                    page=page_num,
                    section=None,
                    original_text=chunk_data.get("raw_visual_description", ""),
                    token_count=len((chunk_data.get("raw_visual_description", "") or "").split()),
                    status="created",
                    active=0,
                    chunk_type=chunk_data.get("chunk_type", "image"),
                    image_artifact_path=chunk_data.get("image_path"),
                    image_hash=chunk_data.get("image_hash"),
                    bounding_box=chunk_data.get("bounding_box"),
                    extraction_method=chunk_data.get("extraction_method"),
                    vision_model=chunk_data.get("vision_model"),
                    vision_prompt_version=chunk_data.get("vision_prompt_version"),
                    raw_visual_description=chunk_data.get("raw_visual_description"),
                    visible_text_draft=chunk_data.get("visible_text_draft"),
                    uncertainty_notes=chunk_data.get("uncertainty_notes"),
                    confidence_score=chunk_data.get("confidence_score"),
                    risk_flags=chunk_data.get("risk_flags", []),
                    admin_status="pending_review",
                )

                db.add(chunk)
                await db.commit()
                await db.refresh(chunk)

                created_chunks.append({
                    "chunk_id": str(chunk.id),
                    "page": page_num,
                    "chunk_type": chunk.chunk_type,
                    "risk_flags": chunk.risk_flags or [],
                })

                logger.info(f"Visual chunk created for page {page_num}")

            except Exception as e:
                logger.error(f"Error creating visual chunk: {e}")
                errors.append(f"Page {page_num}: {str(e)}")
                continue

        return created_chunks, errors

    @staticmethod
    async def _should_process(quality: dict) -> tuple[bool, str]:
        """Determine if image should be processed."""

        quality_level = quality.get("quality", "error")

        if quality_level in ("error", "unreadable"):
            return False, "unreadable_image"

        resolution = quality.get("resolution", "medium")
        contrast = quality.get("contrast", "medium")

        if resolution == "low" and contrast == "low":
            return False, "very_low_quality"

        return True, "acceptable_quality"
