"""Image extractor for PDFs using PyMuPDF and quality assessment via OpenCV."""
import logging
import hashlib
from pathlib import Path
from datetime import datetime

try:
    import fitz
except ImportError:
    fitz = None

import cv2

logger = logging.getLogger(__name__)


class ImageExtractionError(Exception):
    """Image extraction error."""
    pass


class ImageExtractor:
    """Extract images from PDFs with quality assessment."""

    def __init__(self):
        if not fitz:
            raise ImportError("PyMuPDF required")

    async def extract_images_from_pdf(
        self,
        pdf_path: str,
        output_dir: str,
        max_images_per_page: int = 5,
        max_images_total: int = 50,
    ) -> list[dict]:
        """Extract images from PDF with metadata."""

        extracted = []
        image_count = 0

        try:
            doc = fitz.open(pdf_path)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            for page_num, page in enumerate(doc, 1):
                if image_count >= max_images_total:
                    break

                images = page.get_images(full=True)
                page_images = []

                for img_index, img_ref in enumerate(images):
                    if len(page_images) >= max_images_per_page:
                        break
                    if image_count >= max_images_total:
                        break

                    try:
                        xref = img_ref[0]
                        pix = fitz.Pixmap(doc, xref)

                        if pix.n - pix.alpha < 4:
                            pix_rgb = pix
                        else:
                            pix_rgb = fitz.Pixmap(fitz.csRGB, pix)

                        image_data = pix_rgb.tobytes("png")
                        image_hash = hashlib.md5(image_data).hexdigest()

                        if any(m["image_hash"] == image_hash for m in extracted):
                            continue

                        bbox = page.get_image_bbox(img_ref)

                        filename = f"page_{page_num:04d}_img_{img_index:02d}_{image_hash[:8]}.png"
                        filepath = Path(output_dir) / filename

                        with open(filepath, "wb") as f:
                            f.write(image_data)

                        metadata = {
                            "page_number": page_num,
                            "image_index": img_index,
                            "image_hash": image_hash,
                            "image_path": str(filepath),
                            "bounding_box": [bbox.x0, bbox.y0, bbox.x1, bbox.y1],
                            "width": pix_rgb.width,
                            "height": pix_rgb.height,
                            "extraction_method": "pymupdf",
                            "extracted_at": datetime.utcnow().isoformat(),
                        }

                        extracted.append(metadata)
                        page_images.append(metadata)
                        image_count += 1

                    except Exception as e:
                        logger.error(f"Error extracting image {img_index} from page {page_num}: {e}")
                        continue

                logger.info(f"Page {page_num}: extracted {len(page_images)} images")

            doc.close()
            logger.info(f"Total images extracted: {len(extracted)}")
            return extracted

        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            raise ImageExtractionError(f"Failed to extract images: {e}")

    async def extract_table_screenshots_from_pdf(
        self,
        pdf_path: str,
        output_dir: str,
        dpi_scale: float = 2.0,
        max_tables_total: int = 30,
    ) -> list[dict]:
        """Screenshot every vector-drawn table on every page.

        `extract_images_from_pdf` above only pulls embedded raster streams
        (`page.get_images()`) — a table made of drawn lines and positioned text (the
        overwhelmingly common case for tables in Word-exported-to-PDF official documents)
        has no embedded image object at all, so it was never extracted, never reviewable
        by admin, and never a candidate for the active knowledge base. PyMuPDF's native
        `page.find_tables()` (table-structure detection, not OCR) locates these regions by
        their drawn geometry; `page.get_pixmap(clip=...)` then rasterizes exactly that
        region at `dpi_scale`x resolution so the screenshot is sharp enough to read table
        text even when zoomed, not a blurry thumbnail.
        """
        extracted = []

        try:
            doc = fitz.open(pdf_path)
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            matrix = fitz.Matrix(dpi_scale, dpi_scale)

            for page_num, page in enumerate(doc, 1):
                if len(extracted) >= max_tables_total:
                    break
                try:
                    found = page.find_tables()
                except Exception as e:
                    logger.warning(f"Table detection failed on page {page_num}: {e}")
                    continue

                for t_index, table in enumerate(found.tables):
                    if len(extracted) >= max_tables_total:
                        break
                    try:
                        # 4pt margin so table borders/headers aren't clipped at the edge.
                        clip_rect = fitz.Rect(table.bbox) + (-4, -4, 4, 4)
                        pix = page.get_pixmap(matrix=matrix, clip=clip_rect)
                        image_data = pix.tobytes("png")
                        image_hash = hashlib.md5(image_data).hexdigest()

                        if any(m["image_hash"] == image_hash for m in extracted):
                            continue

                        filename = f"page_{page_num:04d}_table_{t_index:02d}_{image_hash[:8]}.png"
                        filepath = Path(output_dir) / filename
                        with open(filepath, "wb") as f:
                            f.write(image_data)

                        extracted.append({
                            "page_number": page_num,
                            "image_index": t_index,
                            "image_hash": image_hash,
                            "image_path": str(filepath),
                            "bounding_box": list(clip_rect),
                            "width": pix.width,
                            "height": pix.height,
                            "extraction_method": "pymupdf_table_screenshot",
                            "extracted_at": datetime.utcnow().isoformat(),
                            "detected_as": "table",
                        })
                    except Exception as e:
                        logger.error(f"Error screenshotting table {t_index} on page {page_num}: {e}")
                        continue

            doc.close()
            logger.info(f"Total table screenshots captured: {len(extracted)}")
            return extracted

        except Exception as e:
            logger.error(f"Table screenshot extraction failed: {e}")
            raise ImageExtractionError(f"Failed to screenshot tables: {e}")

    async def assess_image_quality(self, image_path: str) -> dict:
        """Assess image quality for vision processing."""

        try:
            img = cv2.imread(image_path)
            if img is None:
                return {"quality": "unreadable", "error": "Cannot read image"}

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape

            resolution = "low" if width < 300 or height < 300 else "medium" if width < 1000 else "high"

            contrast = gray.std()
            contrast_level = "low" if contrast < 20 else "medium" if contrast < 50 else "high"

            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            blur_level = "high" if laplacian_var < 50 else "medium" if laplacian_var < 100 else "low"

            is_scanned = resolution == "low" or blur_level == "high"

            return {
                "quality": "good" if contrast_level == "high" and blur_level == "low" else "medium",
                "resolution": resolution,
                "contrast": contrast_level,
                "blur": blur_level,
                "is_scanned": is_scanned,
                "width": width,
                "height": height,
                "laplacian_variance": float(laplacian_var),
            }

        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return {"quality": "error", "error": str(e)}
