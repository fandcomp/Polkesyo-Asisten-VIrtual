"""Read-only indexing-time measurement, part 2: summarization stage.
Calls the real ChunkSummaryService.generate_summary (a pure OpenRouter call, no DB/Chroma/Neo4j
write anywhere in that function) against a few real chunks from an already-extracted document.
Nothing is persisted -- this only measures latency of the LLM call itself.
"""
import asyncio
import time

from app.services.text_extractor import TextExtractor
from app.services.chunking_service import ChunkingService
from app.services.chunk_summary_service import ChunkSummaryService
from app.core.config import settings

FILEPATH = "/app/data/raw/Pedoman_SPMB_Mandiri_Reguler_SMA_Poltekkes_Kemenkes_Yogyakarta_TA_2026-2027_5b8ac6b7.pdf"
N_CHUNKS_TO_SUMMARIZE = 3  # keep small and cheap -- just enough for a real per-chunk timing sample


async def main():
    print(f"chunk_summary_model={settings.chunk_summary_model}")
    text = await TextExtractor.extract_from_file(FILEPATH)
    chunks = ChunkingService.chunk_text(text)
    print(f"total_chunks={len(chunks)}, summarizing first {N_CHUNKS_TO_SUMMARIZE}")

    durations = []
    for i, chunk in enumerate(chunks[:N_CHUNKS_TO_SUMMARIZE]):
        t0 = time.perf_counter()
        summary = await ChunkSummaryService.generate_summary(chunk)
        t1 = time.perf_counter()
        ms = round((t1 - t0) * 1000, 1)
        durations.append(ms)
        ok = summary is not None
        print(f"chunk[{i}] summarize_ms={ms} success={ok} summary_len={len(summary) if summary else 0}")

    avg = round(sum(durations) / len(durations), 1) if durations else None
    print(f"\naverage_summarize_ms_per_chunk={avg}")


asyncio.run(main())
