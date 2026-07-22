"""Synchronize official documents from sources."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.models import Document, DocumentVersion
from app.services.document_downloader import DocumentDownloader
from app.services.document_classifier import DocumentClassifier
from app.core.config import settings


class DocumentSyncService:
    """Orchestrate document synchronization."""

    @staticmethod
    async def sync_official_url(
        db: AsyncSession,
        source_url: str = "https://sipenmaru.poltekkesjogja.ac.id/index.php?mod=login_default&sub=filePanduan&act=view&typ=html",
    ) -> dict:
        """Sync documents from official Sipenmaru URL."""
        result = {
            "total_found": 0,
            "total_new": 0,
            "total_updated": 0,
            "errors": [],
            "started_at": datetime.utcnow(),
        }

        try:
            # For Phase 9, simplified sync:
            # In production, would parse HTML to extract document links
            # For now, log that sync was attempted
            
            result["status"] = "completed"
            result["message"] = "Document sync initialized (link parsing in Phase 9 enhancement)"
            result["finished_at"] = datetime.utcnow()
            
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            result["finished_at"] = datetime.utcnow()

        return result

    @staticmethod
    async def create_document(
        db: AsyncSession,
        title: str,
        document_type: str,
        source_url: str,
        source_type: str = "manual_upload",
        year: int | None = None,
    ) -> Document:
        """Create a new document record."""
        doc = Document(
            id=uuid4(),
            title=title,
            document_type=document_type,
            source_url=source_url,
            source_type=source_type,
            status="discovered",
            year=year,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    async def create_document_version(
        db: AsyncSession,
        document_id: str,
        checksum: str,
        source_url: str | None = None,
        raw_file_path: str | None = None,
    ) -> DocumentVersion:
        """Create a document version record."""
        # Get current version count
        from sqlalchemy import func
        stmt = select(func.max(DocumentVersion.version)).where(
            DocumentVersion.document_id == document_id
        )
        result = await db.execute(stmt)
        max_version = result.scalar() or 0
        
        version = DocumentVersion(
            id=uuid4(),
            document_id=document_id,
            version=max_version + 1,
            checksum=checksum,
            source_url=source_url,
            raw_file_path=raw_file_path,
            status="downloaded",
        )
        db.add(version)
        await db.commit()
        await db.refresh(version)
        return version

    @staticmethod
    async def check_document_exists(
        db: AsyncSession,
        checksum: str,
    ) -> DocumentVersion | None:
        """Check if document version already exists by checksum."""
        stmt = select(DocumentVersion).where(
            DocumentVersion.checksum == checksum
        )
        result = await db.execute(stmt)
        return result.scalars().first()
