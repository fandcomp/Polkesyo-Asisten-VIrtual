"""Detect visual regions and assess document quality."""
import logging

logger = logging.getLogger(__name__)


class VisualRegionDetector:
    """Identify pages with visual content and assess quality."""

    @staticmethod
    async def detect_visual_regions(
        image_quality_results: list[dict],
    ) -> dict:
        """Analyze extracted images to determine visual patterns.

        Args:
            image_quality_results: List of quality assessment results

        Returns:
            Analysis with visual patterns and recommendations
        """

        if not image_quality_results:
            return {
                "has_visual_content": False,
                "visual_types_detected": [],
                "scanned_pages": [],
                "mixed_content_pages": [],
                "quality_summary": "text-only",
            }

        visual_types = []
        scanned_pages = set()
        quality_issues = []

        for result in image_quality_results:
            page_num = result.get("page_number")
            quality = result.get("quality", {})
            is_scanned = quality.get("is_scanned", False)
            resolution = quality.get("resolution", "medium")
            blur = quality.get("blur", "medium")

            if is_scanned:
                scanned_pages.add(page_num)
                visual_types.append("scanned_region")

            if resolution == "low":
                quality_issues.append(f"Page {page_num}: Low resolution")

            if blur == "high":
                quality_issues.append(f"Page {page_num}: High blur")

        return {
            "has_visual_content": len(image_quality_results) > 0,
            "visual_types_detected": list(set(visual_types)),
            "scanned_pages": sorted(list(scanned_pages)),
            "quality_issues": quality_issues,
            "total_images": len(image_quality_results),
            "quality_summary": (
                "good" if not quality_issues
                else "needs_review" if len(quality_issues) < 3
                else "low_quality"
            ),
        }

    @staticmethod
    async def should_extract_visual_description(
        image_quality: dict,
    ) -> tuple[bool, str]:
        """Determine if image should be sent to vision LLM.

        Returns:
            (should_extract, reason)
        """

        quality_level = image_quality.get("quality", "error")
        resolution = image_quality.get("resolution", "medium")
        contrast = image_quality.get("contrast", "medium")

        if quality_level == "error" or quality_level == "unreadable":
            return False, "unreadable_image"

        if resolution == "low" and contrast == "low":
            return False, "very_low_quality"

        return True, "acceptable_quality"

    @staticmethod
    async def categorize_visual_content(
        image_path: str,
        image_quality: dict,
        visible_text_draft: str = "",
    ) -> dict:
        """Categorize the type of visual content."""

        category = "image"
        confidence = 0.5

        resolution = image_quality.get("resolution", "medium")
        is_scanned = image_quality.get("is_scanned", False)

        if is_scanned:
            category = "scanned_region"
            confidence = 0.8 if visible_text_draft else 0.6

        if len(visible_text_draft or "") > 200:
            category = "mixed"
            confidence = 0.9

        return {
            "category": category,
            "confidence": confidence,
            "reasoning": f"Categorized as {category}",
        }
