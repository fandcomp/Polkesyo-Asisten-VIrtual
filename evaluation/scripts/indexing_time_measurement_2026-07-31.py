"""Read-only indexing-time measurement. Does NOT write to DB/Chroma/Neo4j.
Times: extraction, chunking, embedding (throwaway in-memory), entity extraction (regex).
Run inside campus-va-backend container.
"""
import asyncio
import time

from app.services.text_extractor import TextExtractor
from app.services.chunking_service import ChunkingService
from app.services.graph_service import GraphService
from app.services.vector_index_service import VectorIndexService

FILES = [
    "/app/data/raw/Pedoman_SPMB_Mandiri_Reguler_SMA_Poltekkes_Kemenkes_Yogyakarta_TA_2026-2027_5b8ac6b7.pdf",
    "/app/data/raw/2436_PELAKSANAAN_UJIAN_CBT_SPMB_MANDIRI_PROGRAM_STUDI_PROFESI_POLTEKKES_KEMENKES_d81ba0a5.pdf",
]


async def main():
    embed_fn = VectorIndexService.get_embedding_function()
    print(f"using real production embedding function: {type(embed_fn).__name__}")

    for filepath in FILES:
        print(f"\n=== {filepath.split('/')[-1]} ===")
        t0 = time.perf_counter()
        text = await TextExtractor.extract_from_file(filepath)
        t1 = time.perf_counter()
        print(f"extract_ms={round((t1 - t0) * 1000, 1)} chars={len(text)}")

        chunks = ChunkingService.chunk_text(text)
        t2 = time.perf_counter()
        print(f"chunk_ms={round((t2 - t1) * 1000, 1)} n_chunks={len(chunks)}")

        # Entity extraction is a pure regex/keyword function -- safe, no DB write.
        total_entities = 0
        t2b = time.perf_counter()
        for c in chunks:
            ents = GraphService.extract_entities(c)
            total_entities += len(ents)
        t3 = time.perf_counter()
        print(f"entity_extract_ms={round((t3 - t2b) * 1000, 1)} total_entities_found={total_entities}")

        # Embedding via the same default embedding function Chroma uses -- computed
        # in-memory only, never added to any collection (no Chroma write at all).
        t3b = time.perf_counter()
        _ = embed_fn(chunks)
        t4 = time.perf_counter()
        print(f"embed_ms={round((t4 - t3b) * 1000, 1)} (for {len(chunks)} chunks, in-memory only, not indexed)")

        total_ms = round((t4 - t0) * 1000, 1)
        print(f"TOTAL (excl. LLM summarization, not run -- OpenRouter account currently dry)={total_ms}ms")


asyncio.run(main())
