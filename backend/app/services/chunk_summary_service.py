"""Generate LLM-based chunk summaries via OpenRouter."""
import httpx
from app.core.config import settings


class ChunkSummaryService:
    """Generate summaries for document chunks using LLM."""

    SUMMARY_PROMPT = """Summarize the following document chunk concisely in one paragraph.
Only summarize what is explicitly in the chunk - do not add external knowledge.

Always write the summary in formal Indonesian (Bahasa Indonesia baku) — this is the primary
language of this assistant. Translate to Indonesian even if the source chunk itself is in
English or another language; do not leave the summary untranslated. This matters because the
summary is what gets matched against user questions, and the vast majority of user questions
here are in Indonesian.

Preserve these details EXACTLY as written, verbatim, character-for-character — do not
paraphrase, round, or reword them even slightly:
- Article/regulation numbers (e.g. "Pasal 5 ayat 2", "PMK No. 55/2021")
- Dates and deadlines (e.g. "3 Maret 2031", "1-31 Juli 2026")
- Fees and amounts (e.g. "Rp 350.000")
- Locations and addresses
Everything else may be paraphrased for concision, but these specific figures must not change.

If the chunk contains a table (rows of structured data — e.g. participant numbers, schedules,
fees, requirements, marked with "| ... |" rows or a "[Tabel ...]" heading), do NOT summarize it
as a single paraphrased paragraph. Instead, enumerate EVERY row completely and verbatim, one by
one — do not merge, average, sample, or drop any row, even if this makes the summary much
longer than usual. Every data point in a table matters equally; losing even one row is
unacceptable.

Chunk:
{chunk}

Summary:"""

    @staticmethod
    async def generate_summary(
        chunk_text: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str | None:
        """Generate summary using OpenRouter LLM."""
        if not settings.openrouter_api_key:
            return None

        model = model or settings.chunk_summary_model or settings.openrouter_primary_model
        tokens = max_tokens or settings.chunk_summary_max_tokens or 400

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "HTTP-Referer": "https://campus-va.local",
                        "X-Title": "Campus Virtual Assistant",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                # 4000 chars covers a full 500-600 token chunk (CLAUDE.md
                                # §20 chunking config) with margin — 2000 was cutting real
                                # chunks mid-fact for anything past the first ~40% of content.
                                "content": ChunkSummaryService.SUMMARY_PROMPT.format(chunk=chunk_text[:4000])
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": tokens,
                    },
                )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        
        except Exception:
            return None
