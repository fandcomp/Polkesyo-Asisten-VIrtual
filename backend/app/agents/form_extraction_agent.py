"""FormExtractionAgent (structure-aware document extraction plan) — runs on `form_text` zone
pages produced by DocumentStructureAgent. Splits the zone's pages into individual forms (a
form does not always align 1:1 with a page — verified real example: the Daftar Ulang zone has
a checklist on p.30, a registration form spanning p.31-32, and four separate Surat Pernyataan
forms on p.33-36) and renders each one, verbatim, into its own `.docx` via `docx_builder`.

Forms are explicitly NOT chunked/summarized/indexed — see `DocumentFormExtract` (CLAUDE.md
§4.7/§21.6): a generated `.docx` stays `pending_review` until an admin approves it.
"""
import json
import logging
import re
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select

from app.agents.base_agent import BaseAgent
from app.core.config import settings
from app.db.models import Document, DocumentFormExtract
from app.services.ingestion.docx_builder import build_form_docx

# Anything that isn't a letter/digit/space/hyphen/underscore, collapsed — keeps generated
# filenames filesystem-safe on both Windows and Linux (the VPS) without stripping the
# Indonesian document title down to nothing.
_FILENAME_UNSAFE_RE = re.compile(r"[^\w\-]+", re.UNICODE)


def _slugify_title(title: str, max_length: int = 60) -> str:
    slug = _FILENAME_UNSAFE_RE.sub("_", title.strip()).strip("_")
    return (slug[:max_length].rstrip("_")) or "dokumen"

logger = logging.getLogger(__name__)

# A new form's heading is one of these, at the very start of a page/paragraph (verified real
# examples: "SURAT PERNYATAAN", "FORMULIR PEMERIKSAAN KESEHATAN", "FORM ...", "BERKAS ...").
_FORM_HEADING_RE = re.compile(r"^(SURAT PERNYATAAN|FORMULIR|FORM[: ]|BERKAS)", re.IGNORECASE)

# A numbered field line, e.g. "21. Nama lengkap: ..." — used to detect whether a form's
# numbered field sequence continues across a page break (same form) or restarts (new form).
# re.MULTILINE is required: without it, `^` only anchors to the start of the whole string, not
# the start of each line, so every numbered field past the first line would be missed.
_NUMBERED_FIELD_RE = re.compile(r"^(\d{1,2})\.\s", re.MULTILINE)

# Matches the pipe-delimited markdown table rows TextExtractor renders (same shape
# chunking_service.py's own `_TABLE_ROW_RE` recognizes) — kept local rather than importing a
# private module attribute across files.
_TABLE_ROW_RE = re.compile(r"^\|.*\|$")

# Two page-artifact patterns that must never leak into an extracted form (user requirement:
# a generated form should read like a standalone document, not carry source-PDF page markers):
# 1. A line that is *only* a printed page number (e.g. a lone "18" or "24") — PyMuPDF extracts
#    a PDF page's header/footer text alongside its body, and a bare page number consistently
#    turns up at page boundaries with nothing else on the line. Real form field values are
#    never a standalone bare integer at extraction time (these are blank templates — filled-in
#    values are dotted blanks "....", not digits), so this is a safe, unambiguous filter.
# 2. TextExtractor's own synthetic `[Tabel halaman N]` marker (text_extractor.py) — inserted to
#    help the flat-chunking/summary pipeline locate tables, but meaningless (and visibly wrong)
#    inside a verbatim form reproduction.
_PAGE_NUMBER_LINE_RE = re.compile(r"^\d{1,4}$")
_TABLE_PAGE_MARKER_RE = re.compile(r"^\[Tabel halaman \d+\]$")
# The source PDF's own generator watermark ("Powered by TCPDF (www.tcpdf.org)") — found
# leaking into extracted output the same way page numbers do (PDF-tool-inserted page
# furniture, not real form content). Case-insensitive: PDF text extraction can vary casing.
_GENERATOR_WATERMARK_RE = re.compile(r"^Powered by TCPDF \(www\.tcpdf\.org\)$", re.IGNORECASE)

_TIE_BREAK_PROMPT = """Dua halaman berurutan dari sebuah dokumen resmi kampus di bawah ini \
mungkin merupakan bagian dari SATU formulir yang sama, atau dua formulir yang BERBEDA.

Akhir halaman sebelumnya:
{prev_text}

Awal halaman berikutnya:
{curr_text}

Jawab HANYA dengan JSON, tanpa penjelasan lain: {{"same_form": true}} atau {{"same_form": false}}"""


class FormExtractionAgent(BaseAgent):
    name = "FormExtractionAgent"

    async def _run(self, input_data: dict) -> dict:
        db = input_data.get("db")
        document_id = input_data["document_id"]
        document_version_id = input_data["document_version_id"]
        pages: list[dict] = input_data.get("pages") or []
        zone_title: str | None = input_data.get("zone_title")

        if not pages:
            return {"forms": []}

        document_title = "Dokumen"
        if db is not None:
            try:
                document_title = (
                    await db.execute(select(Document.title).where(Document.id == document_id))
                ).scalar_one_or_none() or document_title
            except Exception as exc:
                logger.warning(f"Could not look up document title for {document_id}: {exc}")

        pages = sorted(pages, key=lambda p: p["page"])
        groups = await self._detect_form_boundaries(pages)

        forms: list[dict] = []
        for group in groups:
            title = self._extract_title(group) or zone_title or "Formulir"
            _fields, _tables, items = self._extract_fields_and_tables(group)
            output_path = self._build_output_path(document_title, document_id, group[0]["page"])
            build_form_docx(title, [], [], output_path, items=items)

            forms.append({
                "title": title,
                "start_page": group[0]["page"],
                "end_page": group[-1]["page"],
                "docx_artifact_path": output_path,
            })

            if db is not None:
                try:
                    record = DocumentFormExtract(
                        document_id=document_id,
                        document_version_id=document_version_id,
                        zone_type="form_text",
                        form_title=title,
                        source_page_start=group[0]["page"],
                        source_page_end=group[-1]["page"],
                        extraction_method="text",
                        docx_artifact_path=output_path,
                        status="pending_review",
                    )
                    db.add(record)
                    await db.commit()
                except Exception as exc:
                    logger.error(f"Failed to persist document_form_extracts for '{title}': {exc}")

        return {"forms": forms}

    @staticmethod
    async def _detect_form_boundaries(pages: list[dict]) -> list[list[dict]]:
        groups: list[list[dict]] = [[pages[0]]]
        for prev_page, curr_page in zip(pages, pages[1:]):
            if await FormExtractionAgent._same_form(prev_page, curr_page):
                groups[-1].append(curr_page)
            else:
                groups.append([curr_page])
        return groups

    @staticmethod
    async def _same_form(prev_page: dict, curr_page: dict) -> bool:
        curr_text = (curr_page.get("text") or "").strip()
        curr_first_line = curr_text.splitlines()[0].strip() if curr_text else ""

        # A new heading at the top of this page is a strong "new form" signal.
        if _FORM_HEADING_RE.match(curr_first_line):
            return False

        prev_numbers = _NUMBERED_FIELD_RE.findall(prev_page.get("text") or "")
        curr_numbers = _NUMBERED_FIELD_RE.findall(curr_text)
        if prev_numbers and curr_numbers:
            # Sequential numbering across the page break (item 21 -> 22) is the verified real
            # signal that this is the SAME form continuing (Daftar Ulang zone, p.31->32),
            # while a restart (item 1 again on p.31 after p.30 ended differently) means a new
            # form started (p.30->31).
            try:
                return int(curr_numbers[0]) == int(prev_numbers[-1]) + 1
            except ValueError:
                pass

        # Ambiguous: no heading match and no usable numbering signal — ask the LLM. Same
        # low-temperature structured-JSON tie-break pattern already used elsewhere
        # (vision_description_service.py, chunk_summary_service.py), so no new calling
        # convention is introduced.
        return await FormExtractionAgent._llm_tie_break(prev_page, curr_page)

    @staticmethod
    async def _llm_tie_break(prev_page: dict, curr_page: dict) -> bool:
        if not settings.openrouter_api_key:
            # No LLM available (tests, local dev without a key) — default to treating an
            # ambiguous page break as a NEW form. This is the safer assumption: it never
            # silently merges two distinct official forms into one, at worst it over-splits.
            return False

        prompt = _TIE_BREAK_PROMPT.format(
            prev_text=(prev_page.get("text") or "")[-1500:],
            curr_text=(curr_page.get("text") or "")[:1500],
        )
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
                        "model": settings.chunk_summary_model or settings.openrouter_primary_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                        "max_tokens": 20,
                    },
                )
                if response.status_code != 200:
                    return False
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                stripped = content.strip().strip("`")
                if stripped.lower().startswith("json"):
                    stripped = stripped[4:].strip()
                parsed = json.loads(stripped)
                return bool(parsed.get("same_form", False))
        except Exception as exc:
            logger.warning(f"Form boundary tie-break LLM call failed, defaulting to new form: {exc}")
            return False

    @staticmethod
    def _extract_title(group: list[dict]) -> str | None:
        for line in (group[0].get("text") or "").splitlines():
            stripped = line.strip()
            if _FORM_HEADING_RE.match(stripped):
                return stripped
        return None

    @staticmethod
    def _extract_fields_and_tables(
        group: list[dict],
    ) -> tuple[list[tuple[str, str]], list[list[list[str]]], list[tuple[str, object]]]:
        """Verbatim field/table extraction — no paraphrasing (CLAUDE.md §21.5 applies to
        summaries, not to these excluded-from-chunking form pages, and the user was explicit:
        "isinya table persis sesuai di file dokumen pedoman itu").

        Returns `(fields, tables, items)`: `fields`/`tables` are kept for backward
        compatibility with any caller still consuming them separately (grouped by kind,
        original ordering lost between the two groups). `items` is the ordered sequence of
        `("field", (label, value))` / `("table", rows)` entries in their real
        as-they-appear-in-the-document order — this is what `build_form_docx` now renders
        from, since a form and its accompanying table are rarely just "all the fields, then
        all the tables" in the source (2026-07-22 fix: the previous fields-then-tables split
        silently reordered content relative to the original document, which is the opposite
        of the verbatim requirement above)."""
        fields: list[tuple[str, str]] = []
        tables: list[list[list[str]]] = []
        items: list[tuple[str, object]] = []
        current_table: list[list[str]] = []

        def flush_table() -> None:
            nonlocal current_table
            if current_table:
                tables.append(current_table)
                items.append(("table", current_table))
                current_table = []

        for page in group:
            for line in (page.get("text") or "").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if (
                    _PAGE_NUMBER_LINE_RE.match(stripped)
                    or _TABLE_PAGE_MARKER_RE.match(stripped)
                    or _GENERATOR_WATERMARK_RE.match(stripped)
                ):
                    continue
                if _TABLE_ROW_RE.match(stripped):
                    cells = [c.strip() for c in stripped.strip("|").split("|")]
                    if not all(c in ("", "---") for c in cells):
                        current_table.append(cells)
                    continue
                flush_table()
                if ":" in stripped:
                    label, _, value = stripped.partition(":")
                    field = (label.strip(), value.strip())
                else:
                    field = (stripped, "")
                fields.append(field)
                items.append(("field", field))
        flush_table()
        return fields, tables, items

    @staticmethod
    def _build_output_path(document_title: str, document_id, start_page: int) -> str:
        """Filename now carries the source document's title (user requirement: identify a
        form extract's origin from the filename alone, without needing a separate index) —
        `document_id`'s directory-per-document layout stays as the collision-proof storage
        path underneath, the title only changes the human-facing filename."""
        output_dir = Path(settings.processed_document_storage_path) / str(document_id) / "forms"
        output_dir.mkdir(parents=True, exist_ok=True)
        slug = _slugify_title(document_title)
        filename = f"{slug}_p{start_page:04d}_{uuid4().hex[:8]}.docx"
        return str(output_dir / filename)
