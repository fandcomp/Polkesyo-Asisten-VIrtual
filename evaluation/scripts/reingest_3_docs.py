"""One-off: re-ingest 3 documents affected by the chunking section-boundary bug fix
(2026-07-25). Creates a new DocumentVersion (same file) per document, re-chunks with the
FIXED chunking_service.py (text only -- include_visual_chunks=False, since visual chunks
are unaffected by the bug and re-running them has no dedup-by-image_hash), re-summarizes
new chunks via OpenRouter, marks old TEXT chunks superseded (visual chunks are left alone
on the old version), bulk-approves the new ones (mirrors the 2026-07-15
bulk_approve_all.py precedent -- no plaintext admin HTTP password available), reindexes
Chroma+Neo4j per document, flushes the vector retrieval cache. Run inside
campus-va-backend via docker exec.

Pass document ID prefixes as argv to run a subset (e.g. a single-document smoke test
before running all 3): `python reingest_3_docs.py 1e05c30d`
"""
import asyncio
import hashlib
import sys

DOCUMENT_IDS = [
    "1e05c30d-3972-42eb-9db4-f3e5d345edc0",
    "a24235d6-b31f-4112-a8f5-bde31a3b5ccc",
    "04a2aa5a-6c70-4a2e-91df-86e39b804409",
]

if len(sys.argv) > 1:
    DOCUMENT_IDS = [d for d in DOCUMENT_IDS if any(d.startswith(prefix) for prefix in sys.argv[1:])]
    if not DOCUMENT_IDS:
        raise SystemExit(f"No document IDs matched prefixes: {sys.argv[1:]}")


async def main() -> None:
    from sqlalchemy import select, func
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.core.config import settings
    from app.db.models import Document, DocumentVersion, DocumentChunk, ChunkSummary
    from app.services.ingestion_service import IngestionService
    from app.services.vector_index_service import VectorIndexService
    from app.services.graph_service import GraphService

    engine = create_async_engine(settings.database_url)
    db_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with db_factory() as db:
        for doc_id in DOCUMENT_IDS:
            print(f"\n=== {doc_id} ===")
            doc = (await db.execute(select(Document).where(Document.id == doc_id))).scalar_one()
            latest = (
                await db.execute(
                    select(DocumentVersion)
                    .where(DocumentVersion.document_id == doc_id)
                    .order_by(DocumentVersion.version.desc())
                    .limit(1)
                )
            ).scalar_one()
            old_version_id = str(latest.id)

            new_version_number = latest.version + 1
            # document_versions has UNIQUE(document_id, checksum) -- the file itself is
            # unchanged (only chunking logic changed), so reusing latest.checksum verbatim
            # would violate that constraint. Derive a synthetic, distinct 64-hex-char
            # checksum instead; it does not claim to be a real content hash.
            rechunk_checksum = hashlib.sha256(
                f"{latest.checksum}:rechunk:v{new_version_number}".encode()
            ).hexdigest()
            new_version = DocumentVersion(
                document_id=doc_id,
                version=new_version_number,
                checksum=rechunk_checksum,
                source_url=latest.source_url,
                raw_file_path=latest.raw_file_path,
                status="created",
            )
            db.add(new_version)
            await db.commit()
            await db.refresh(new_version)
            print(f"  new version {new_version.version} ({new_version.id}), old={old_version_id}")

            result = await IngestionService.ingest_document(
                db, str(new_version.id), doc_id, latest.raw_file_path,
                include_visual_chunks=False,
            )
            print(f"  ingest result: {result}")
            if result.get("error"):
                print("  SKIPPING rest of this document due to ingest error")
                continue

            # Supersede old TEXT chunks only (CLAUDE.md 21.6 -- must leave active retrieval).
            # Visual chunks (chunk_type != "text") are untouched by include_visual_chunks=False
            # above and must keep their normal status="created"/admin_status-governed state --
            # they were never part of this document's re-ingestion.
            old_chunks = (
                await db.execute(
                    select(DocumentChunk).where(
                        DocumentChunk.document_version_id == old_version_id,
                        DocumentChunk.chunk_type == "text",
                    )
                )
            ).scalars().all()
            old_chunk_ids = [str(c.id) for c in old_chunks]
            for c in old_chunks:
                c.status = "superseded"
            await db.commit()
            print(f"  superseded {len(old_chunks)} old chunks")

            # Remove the superseded chunks from Chroma too -- index_approved_chunks only
            # upserts, it never deletes, so without this the old vectors stay retrievable
            # forever with a frozen metadata["status"]="approved" that never learns about
            # the Postgres status change (see VectorIndexService.remove_chunks_from_index
            # docstring). Confirmed empirically 2026-07-26: all 9 old chunks from the first
            # reingest attempt were still live in Chroma and one was actually selected into
            # a real answer's context.
            deindex_result = await VectorIndexService.remove_chunks_from_index(old_chunk_ids)
            print(f"  de-indexed from Chroma: {deindex_result}")

            # Bulk-approve new chunks (mirrors bulk_approve_all.py's in-process logic).
            new_chunks = (
                await db.execute(select(DocumentChunk).where(DocumentChunk.document_version_id == str(new_version.id)))
            ).scalars().all()
            approved_n = 0
            for c in new_chunks:
                c.status = "approved"
                summary = (
                    await db.execute(select(ChunkSummary).where(ChunkSummary.chunk_id == c.id))
                ).scalar_one_or_none()
                if summary and summary.llm_summary_draft and not summary.approved_summary:
                    summary.approved_summary = summary.admin_edited_summary or summary.llm_summary_draft
                    summary.summary_status = "approved"
                    approved_n += 1
            await db.commit()
            print(f"  approved {len(new_chunks)} new chunks ({approved_n} summaries promoted)")

            vec_result = await VectorIndexService.index_approved_chunks(db, document_id=doc_id)
            print(f"  vector index: {vec_result}")
            graph_result = await GraphService.index_document_by_id(db, doc_id)
            print(f"  graph index: {graph_result}")

    await engine.dispose()

    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url)
        keys = await r.keys("vector:*")
        if keys:
            await r.delete(*keys)
        print(f"\nFlushed {len(keys)} vector:* cache keys")
        await r.aclose()
    except Exception as e:
        print(f"\nCache flush skipped/failed (non-fatal): {e}")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())
