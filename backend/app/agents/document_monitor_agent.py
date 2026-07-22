"""DocumentMonitorAgent (CLAUDE.md §11A.3) — real implementation replacing the
DocumentSyncService.sync_official_url stub.

Fetches the official SPMB document listing page, parses it, downloads new/changed documents, and
never auto-approves anything (CLAUDE.md §21.9 non-negotiable — lands as `discovered`, admin review
required before any document/chunk becomes active knowledge).

Markup confirmed by a live fetch during implementation (2026-07-02): each document is an
`<a href="/index.php?...&sub=streamData&...&dataId=N" title="...">` inside a
`.column.is-one-quarter` block. The `streamData?dataId=N` URL is itself the direct file download
(confirmed via HEAD request: `Content-Type: application/pdf`,
`Content-Disposition: attachment; filename=...`) — no separate "detail page" hop is needed. The
full `streamData` URL (stored in the existing `Document.source_url` column) is the stable
per-document identifier used to diff "new" vs. "already known" across runs.
"""
import logging
import re
from datetime import datetime
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.db.models import Document, DocumentSource, DocumentVersion
from app.services.document_downloader import DocumentDownloader
from app.services.document_sync_service import DocumentSyncService
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


class DocumentMonitorAgent(BaseAgent):
    name = "DocumentMonitorAgent"

    async def _run(self, input_data: dict) -> dict:
        db: AsyncSession = input_data["db"]
        source_url: str = input_data.get("source_url", settings.document_sync_source_url)

        result = {
            "total_found": 0,
            "total_new": 0,
            "total_updated": 0,
            "total_unchanged": 0,
            "documents": [],
            "errors": [],
        }

        await self._touch_source(db, source_url)

        try:
            listing_html = await self._fetch_listing(source_url)
        except Exception as exc:
            logger.error(f"Failed to fetch document listing from {source_url}: {exc}")
            result["errors"].append(f"Failed to fetch listing page: {exc}")
            return result

        links = self._parse_listing(listing_html, base_url=source_url)
        result["total_found"] = len(links)

        for link in links:
            try:
                outcome = await self._process_link(db, link)
                result[f"total_{outcome['status']}"] = result.get(f"total_{outcome['status']}", 0) + 1
                result["documents"].append(outcome)
            except Exception as exc:
                logger.error(f"Failed to process document link {link['url']}: {exc}")
                result["errors"].append(f"{link['title']}: {exc}")

        return result

    @staticmethod
    async def _touch_source(db: AsyncSession, source_url: str) -> None:
        """Upsert the document_sources row (CLAUDE.md §23.1) and stamp last_checked_at."""
        stmt = select(DocumentSource).where(DocumentSource.source_url == source_url)
        result = await db.execute(stmt)
        source = result.scalars().first()
        if source is None:
            source = DocumentSource(
                source_name="SPMB Poltekkes Kemenkes Yogyakarta",
                source_url=source_url,
                source_type="official_sync",
            )
            db.add(source)
        source.last_checked_at = datetime.utcnow()
        await db.commit()

    @staticmethod
    async def _fetch_listing(source_url: str) -> str:
        headers = {"User-Agent": settings.document_sync_user_agent}
        async with httpx.AsyncClient(timeout=settings.document_sync_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(source_url, headers=headers)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _parse_listing(html: str, base_url: str) -> list[dict]:
        """Extract document links. Defensive: logs what it found instead of crashing on
        unexpected markup, since this depends on a third-party site we don't control."""
        soup = BeautifulSoup(html, "html.parser")
        links = []

        anchors = soup.find_all("a", href=re.compile(r"sub=streamData"))
        for anchor in anchors:
            href = anchor.get("href", "")
            title = anchor.get("title") or anchor.get_text(strip=True) or "Untitled document"
            if not href:
                continue
            full_url = urljoin(base_url, href)
            data_id_match = re.search(r"dataId=(\d+)", href)
            links.append({
                "url": full_url,
                "title": title.strip(),
                "data_id": data_id_match.group(1) if data_id_match else None,
            })

        logger.info(f"DocumentMonitorAgent parsed {len(links)} document links from listing page")
        return links

    @staticmethod
    async def _process_link(db: AsyncSession, link: dict) -> dict:
        existing_doc = await DocumentMonitorAgent._find_by_source_url(db, link["url"])

        data = await DocumentDownloader.download_file(link["url"])
        if data is None:
            return {"url": link["url"], "title": link["title"], "status": "errors", "reason": "download_failed"}

        checksum = DocumentDownloader.compute_checksum(data)

        if existing_doc is not None:
            latest_version = await DocumentMonitorAgent._latest_version(db, existing_doc.id)
            if latest_version and latest_version.checksum == checksum:
                return {"url": link["url"], "title": link["title"], "status": "unchanged", "document_id": str(existing_doc.id)}

            # Known document, changed content -> new version, never overwrite (CLAUDE.md §21.7).
            filename = DocumentMonitorAgent._safe_filename(link, checksum)
            filepath = await DocumentDownloader.save_file(filename, data)
            version = await DocumentSyncService.create_document_version(
                db, document_id=str(existing_doc.id), checksum=checksum,
                source_url=link["url"], raw_file_path=filepath,
            )
            await DocumentMonitorAgent._auto_ingest(db, version.id, existing_doc.id, filepath, link["title"])
            return {"url": link["url"], "title": link["title"], "status": "updated", "document_id": str(existing_doc.id)}

        # Brand new document.
        document_type = "Lainnya"
        try:
            from app.agents.document_classifier_agent import DocumentClassifierAgent
            classification = await DocumentClassifierAgent().execute({"filename": link["title"], "title": link["title"]})
            if classification.output:
                document_type = classification.output["document_type"]
        except Exception as exc:
            logger.warning(f"Classification failed for {link['title']}, defaulting to Lainnya: {exc}")

        doc = await DocumentSyncService.create_document(
            db, title=link["title"], document_type=document_type,
            source_url=link["url"], source_type="official_sync",
        )
        filename = DocumentMonitorAgent._safe_filename(link, checksum)
        filepath = await DocumentDownloader.save_file(filename, data)
        version = await DocumentSyncService.create_document_version(
            db, document_id=str(doc.id), checksum=checksum,
            source_url=link["url"], raw_file_path=filepath,
        )
        await DocumentMonitorAgent._auto_ingest(db, version.id, doc.id, filepath, link["title"])
        return {"url": link["url"], "title": link["title"], "status": "new", "document_id": str(doc.id), "document_type": document_type}

    @staticmethod
    async def _auto_ingest(db: AsyncSession, version_id, document_id, filepath: str, title: str) -> None:
        """Extract->chunk->summarize (including vision extraction for PDFs) right away for a
        newly synced/updated document, instead of leaving it at chunk_count=0 until an admin
        manually clicks "Proses Dokumen" for it. Never raises: a failure here must not break
        sync for the remaining links in this batch — the document still exists and can be
        retried via the manual ingest action, the same fallback the manual-upload path
        (routes_admin.py::upload_document) already relies on."""
        try:
            await IngestionService.ingest_document(db, str(version_id), str(document_id), filepath)
        except Exception as exc:
            logger.warning(f"Auto-ingest failed for {title}: {exc}")

    @staticmethod
    async def _find_by_source_url(db: AsyncSession, source_url: str) -> Document | None:
        stmt = select(Document).where(Document.source_url == source_url)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def _latest_version(db: AsyncSession, document_id) -> DocumentVersion | None:
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    def _safe_filename(link: dict, checksum: str) -> str:
        base = re.sub(r"[^a-zA-Z0-9_-]+", "_", link["title"])[:80].strip("_") or "document"
        return f"{base}_{checksum[:8]}.pdf"
