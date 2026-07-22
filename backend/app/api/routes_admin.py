"""Admin routes for document and system management."""
from uuid import UUID
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.db.models import Document, DocumentChunk, DocumentSource, DocumentVersion
from app.services.document_sync_service import DocumentSyncService
from app.services.document_downloader import DocumentDownloader
from app.services.document_classifier import DocumentClassifier
from app.services.ingestion_service import IngestionService
from app.services.vector_index_service import VectorIndexService
from app.services.graph_service import GraphService
from app.services.document_management_service import DocumentManagementService
from app.core.config import settings
from app.core.security import AdminIdentity, get_current_admin
from sqlalchemy import func, select

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me")
async def get_admin_identity(admin: AdminIdentity = Depends(get_current_admin)):
    """Identify the currently authenticated admin and their Evaluation sub-tab access, so the
    frontend can hide nav tabs a restricted account can't use (the real enforcement is the
    per-route 403 in routes_evaluation_admin.py — this is UX only)."""
    return {
        "username": admin.username,
        "evaluation_tabs": sorted(admin.evaluation_tabs) if admin.evaluation_tabs is not None else None,
    }


@router.get("/documents/sources")
async def list_document_sources(db: AsyncSession = Depends(get_db)):
    """List monitored official document sources (CLAUDE.md §23.1)."""
    stmt = select(DocumentSource).order_by(DocumentSource.created_at.desc())
    result = await db.execute(stmt)
    sources = result.scalars().all()
    return {
        "total": len(sources),
        "sources": [
            {
                "id": str(s.id),
                "source_name": s.source_name,
                "source_url": s.source_url,
                "source_type": s.source_type,
                "is_active": s.is_active,
                "last_checked_at": s.last_checked_at.isoformat() if s.last_checked_at else None,
            }
            for s in sources
        ],
    }


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = "",
    document_type: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Upload a document manually.

    `document_type`, when provided, is an explicit admin override validated
    against `DocumentClassifier.ALLOWED_TYPES` (CLAUDE.md §21.3: classification
    must be admin-editable). When omitted, falls back to automatic classification.
    """
    allowed_ext = settings.allowed_upload_extensions or "pdf,docx,html"
    file_ext = file.filename.split(".")[-1].lower() if file.filename else ""

    if file_ext not in allowed_ext.split(","):
        raise HTTPException(status_code=400, detail="File type not allowed")

    if document_type is not None and document_type not in DocumentClassifier.ALLOWED_TYPES:
        allowed = ", ".join(sorted(DocumentClassifier.ALLOWED_TYPES))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document_type '{document_type}'. Allowed: {allowed}",
        )

    max_size = (settings.max_upload_file_size_mb or 25) * 1024 * 1024
    content = await file.read()

    if len(content) > max_size:
        raise HTTPException(status_code=413, detail="File too large")

    checksum = DocumentDownloader.compute_checksum(content)

    existing = await DocumentSyncService.check_document_exists(db, checksum)
    if existing:
        return {"error": "Document already exists", "checksum": checksum}

    filepath = await DocumentDownloader.save_file(
        f"upload_{checksum[:8]}_{file.filename}",
        content
    )

    doc_type = document_type or DocumentClassifier.classify(file.filename, title)

    doc = await DocumentSyncService.create_document(
        db,
        title=title or file.filename,
        document_type=doc_type,
        source_url=None,
        source_type="manual_upload",
    )
    
    version = await DocumentSyncService.create_document_version(
        db,
        document_id=doc.id,
        checksum=checksum,
        raw_file_path=filepath,
    )

    # Auto-trigger extract→chunk→summarize (including image/vision extraction for PDFs, see
    # ingestion_service.py's _ingest_visual_chunks) right away, instead of requiring a second,
    # separate API call before any chunk — text or visual — exists to review. Never raises:
    # a failure here must not break the upload response; the document still exists and can be
    # retried via the frontend's "Proses Dokumen" button (chunk_count stays 0 until then).
    ingestion_result = None
    try:
        ingestion_result = await IngestionService.ingest_document(
            db, str(version.id), str(doc.id), filepath
        )
    except Exception as e:
        ingestion_result = {"status": "error", "error": str(e)}

    return {
        "document_id": str(doc.id),
        "version_id": str(version.id),
        "filename": file.filename,
        "type": doc_type,
        "checksum": checksum,
        "status": "pending_review",
        "ingestion": ingestion_result,
    }


@router.post("/ingestion/ingest-document/{version_id}")
async def ingest_document(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a document version: extract → chunk → summarize."""
    # Get version record
    stmt = select(DocumentVersion).where(DocumentVersion.id == version_id)
    result = await db.execute(stmt)
    version = result.scalars().first()
    
    if not version:
        raise HTTPException(status_code=404, detail="Document version not found")
    
    if not version.raw_file_path:
        raise HTTPException(status_code=400, detail="No file path for this version")
    
    # Run ingestion pipeline
    result = await IngestionService.ingest_document(
        db,
        str(version.id),
        str(version.document_id),
        version.raw_file_path,
    )
    
    return result


# Chunk statuses that still require admin review before indexing — text-chunk workflow
# (routes_chunk_review.py mutates DocumentChunk.status).
PENDING_TEXT_CHUNK_STATUSES = ("created", "summary_drafted", "pending_review")

# Visual chunk types and their pending statuses — visual-chunk workflow (routes_visual_chunks_
# admin.py mutates DocumentChunk.admin_status, never .status). Must stay in sync with the same
# lists in routes_visual_chunks_admin.py::get_pending_visual_chunks.
VISUAL_CHUNK_TYPES = ("image", "scanned_region", "diagram", "table_image")
PENDING_VISUAL_CHUNK_STATUSES = ("pending_review", "needs_revision")


@router.get("/documents")
async def list_documents(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List documents, optionally filtered by (derived) status, with chunk counts and latest version."""
    stmt = select(Document).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    docs = result.scalars().all()

    # Text chunks: pending is tracked via `status`. Visual chunks (image/table_image/diagram/
    # scanned_region) are reviewed via `admin_status` instead — `status` is set once at
    # ingestion ("created") and never updated again for them, so counting only `status` here
    # would mark every visual chunk pending forever regardless of real review state.
    pending_text_stmt = (
        select(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .where(
            DocumentChunk.chunk_type.notin_(VISUAL_CHUNK_TYPES),
            DocumentChunk.status.in_(PENDING_TEXT_CHUNK_STATUSES),
        )
        .group_by(DocumentChunk.document_id)
    )
    pending_visual_stmt = (
        select(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .where(
            DocumentChunk.chunk_type.in_(VISUAL_CHUNK_TYPES),
            DocumentChunk.admin_status.in_(PENDING_VISUAL_CHUNK_STATUSES),
        )
        .group_by(DocumentChunk.document_id)
    )
    pending_text_result = await db.execute(pending_text_stmt)
    pending_visual_result = await db.execute(pending_visual_stmt)

    pending_counts: dict = {}
    for doc_id, count in pending_text_result.all():
        pending_counts[doc_id] = pending_counts.get(doc_id, 0) + count
    for doc_id, count in pending_visual_result.all():
        pending_counts[doc_id] = pending_counts.get(doc_id, 0) + count

    total_stmt = (
        select(DocumentChunk.document_id, func.count(DocumentChunk.id))
        .group_by(DocumentChunk.document_id)
    )
    total_result = await db.execute(total_stmt)
    total_counts = {doc_id: count for doc_id, count in total_result.all()}

    # Latest (highest-version) DocumentVersion.id per document — used by the
    # frontend to trigger ingestion for documents that have never been chunked.
    latest_version_stmt = select(
        DocumentVersion.document_id,
        DocumentVersion.id,
        DocumentVersion.version,
    ).order_by(DocumentVersion.document_id, DocumentVersion.version.desc())
    latest_version_result = await db.execute(latest_version_stmt)
    latest_version_ids: dict = {}
    for doc_id, version_id, _version in latest_version_result.all():
        latest_version_ids.setdefault(doc_id, str(version_id))

    def effective_status(d: Document) -> str:
        # Document.status is set once at creation ("discovered" by default) and is only ever
        # updated again via the explicit PATCH /admin/documents/{id}/status admin action
        # (e.g. an admin manually rejecting/archiving a document) — nothing in the ingestion/
        # chunk-review pipeline advances it automatically. So: if an admin has explicitly set
        # a real status, respect it; otherwise derive a live one from actual chunk/review
        # state instead of leaving every document stuck showing "discovered" forever.
        if d.status != "discovered":
            return d.status
        chunk_count = total_counts.get(d.id, 0)
        if chunk_count == 0:
            return "discovered"
        return "pending_review" if pending_counts.get(d.id, 0) > 0 else "approved"

    documents = [
        {
            "id": str(d.id),
            "title": d.title,
            "type": d.document_type,
            "status": effective_status(d),
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "pending_chunk_count": pending_counts.get(d.id, 0),
            "chunk_count": total_counts.get(d.id, 0),
            "latest_version_id": latest_version_ids.get(d.id),
        }
        for d in docs
    ]
    if status:
        documents = [doc for doc in documents if doc["status"] == status]
    return documents


@router.get("/stats/summary")
async def get_stats_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate document/chunk/vector-index counts for the monitoring dashboard.

    `/health` only confirms Chroma connectivity (`client.heartbeat()`), not whether the active
    collection actually contains any vectors — this adds the real count so "chroma: ok" can't
    be mistaken for "content is indexed and searchable."
    """
    stats = await DocumentManagementService.get_stats_summary(db)
    stats["vector_index"] = await VectorIndexService.get_active_count()
    return stats


@router.post("/indexing/run")
async def trigger_indexing(
    document_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Index approved chunks into active Chroma collection."""
    result = await VectorIndexService.index_approved_chunks(
        db,
        str(document_id) if document_id else None,
    )
    return result


@router.post("/indexing/rebuild")
async def rebuild_index(db: AsyncSession = Depends(get_db)):
    """Drop and rebuild the entire active Chroma collection from approved chunks.

    Required after changing EMBEDDING_MODEL_NAME (old vectors are not comparable with
    new-query embeddings). Approved-only guarantees are inherited from the indexers —
    this re-embeds representations, it never changes knowledge-approval state.
    """
    from app.services.redis_cache_service import get_cache_service

    result = await VectorIndexService.rebuild_active_collection(db)
    try:
        cache_service = await get_cache_service()
        await cache_service.invalidate_retrieval_cache()
    except Exception:
        pass  # cache invalidation is best-effort; TTL bounds staleness anyway
    return result


@router.post("/graph/index-document")
async def index_document_graph(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Index document entities and relationships into Neo4j."""
    result = await GraphService.index_document_by_id(db, str(document_id))
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
