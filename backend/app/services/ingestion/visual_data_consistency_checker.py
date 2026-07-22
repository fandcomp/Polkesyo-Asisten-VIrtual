"""Compare a visual chunk's extracted data against the same document's text chunks and
flag factual conflicts (a date/fee/number stated differently in each source) so admin
review shows a clear reason instead of requiring the admin to manually cross-check every
figure between a scanned image and the document's regular text.

Not a retrieval-time gate (unlike ACIF Gate 3's graph-document consistency check) — this
runs once at ingestion time, purely to help the human reviewer, and never blocks/rejects
anything on its own. The admin still makes the final call.
"""
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk
from app.services.openrouter_client import OpenRouterClient

logger = logging.getLogger(__name__)

CHECK_PROMPT_TEMPLATE = """Anda adalah pemeriksa konsistensi data untuk sistem asisten virtual kampus.

Bandingkan DATA yang diekstrak dari sebuah gambar/tabel dengan teks dokumen yang sama.
Tugas Anda HANYA mendeteksi apakah ada KONFLIK FAKTUAL — yaitu fakta yang sama (tanggal,
biaya, nomor, nama, persyaratan) disebutkan dengan NILAI BERBEDA di kedua sumber untuk hal
yang sama. Informasi yang hanya disebutkan di salah satu sumber saja BUKAN konflik — itu
wajar dan tidak perlu dilaporkan.

DATA DARI GAMBAR/TABEL:
{visual_text}

TEKS DOKUMEN (potongan relevan):
{document_text}

Kembalikan HANYA JSON, tanpa teks lain:
{{"conflict_detected": true/false, "reason": "..."}}

Jika conflict_detected true, "reason" harus spesifik: sebutkan fakta apa yang
bertentangan dan kedua nilainya (contoh: "Biaya pendaftaran di gambar tertulis
Rp 500.000, namun di teks dokumen tertulis Rp 300.000 untuk jalur yang sama").
Jika false, "reason" boleh string kosong.
"""

# Bounds keep the prompt well within ACIF_MAX_PROMPT_INPUT_TOKENS-scale budgets and the
# per-call cost predictable — a full-document dump isn't needed, just enough text chunks
# to plausibly cover the same facts the visual chunk mentions.
_MAX_TEXT_CHUNKS = 10
_MAX_VISUAL_CHARS = 2000
_MAX_DOCUMENT_CHARS = 6000


class VisualDataConsistencyChecker:
    """Ingestion-time helper — never gates retrieval, only informs admin review."""

    @staticmethod
    async def check(
        visual_text: str,
        document_text_chunks: list[str],
        db: AsyncSession | None = None,
    ) -> dict:
        """Returns {"conflict_detected": bool, "reason": str}. Fails open (no conflict
        reported) on any error — a broken consistency check must never block ingestion
        or masquerade as a real finding."""
        if not visual_text or not document_text_chunks:
            return {"conflict_detected": False, "reason": ""}

        combined_text = "\n---\n".join(document_text_chunks)[:_MAX_DOCUMENT_CHARS]
        prompt = CHECK_PROMPT_TEMPLATE.format(
            visual_text=visual_text[:_MAX_VISUAL_CHARS],
            document_text=combined_text,
        )

        try:
            result = await OpenRouterClient.generate(prompt, db=db, max_tokens=400, temperature=0.0)
            text = result.text.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:]
            parsed = json.loads(text.strip())
            return {
                "conflict_detected": bool(parsed.get("conflict_detected", False)),
                "reason": str(parsed.get("reason") or ""),
            }
        except Exception as e:
            logger.warning(f"Visual data consistency check failed, skipping: {e}")
            return {"conflict_detected": False, "reason": ""}

    @staticmethod
    async def check_visual_chunk_against_document(
        db: AsyncSession,
        visual_chunk: DocumentChunk,
        document_id: str,
    ) -> dict:
        """Convenience wrapper: fetch the document's own text chunks and run the check."""
        stmt = (
            select(DocumentChunk.original_text)
            .where(DocumentChunk.document_id == document_id, DocumentChunk.chunk_type == "text")
            .limit(_MAX_TEXT_CHUNKS)
        )
        text_chunks = [t for t in (await db.execute(stmt)).scalars().all() if t]
        visual_text = visual_chunk.visible_text_draft or visual_chunk.raw_visual_description or ""
        return await VisualDataConsistencyChecker.check(visual_text, text_chunks, db=db)
