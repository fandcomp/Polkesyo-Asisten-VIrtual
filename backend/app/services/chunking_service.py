"""Chunk documents into overlapping segments."""
import re

from app.core.config import settings

# Recursive-splitter separator hierarchy, coarsest to finest — the standard, well-proven
# approach for structure-aware chunking (RecursiveCharacterTextSplitter pattern). Tried in
# order; a piece too big for the token budget is re-split with the NEXT separator down the
# list, never falling back to raw word-count cuts unless every structural/sentence boundary
# has been exhausted. The first two entries are specific to this corpus's official-document
# template (found via direct audit of Pedoman/Pengumuman/Brosur SPMB documents): lettered
# section headings ("C. Mekanisme Pendaftaran") and numbered list points ("9. Apabila...")
# are the corpus's actual structural units, not just generic paragraph breaks.
_SECTION_HEADING_RE = re.compile(r"(?:^|\n)\s*([A-Z]\.\s{1,3}[A-Z][a-zA-Z ]{3,80})")
_NUMBERED_ITEM_SEP = re.compile(r"\n(?=\d{1,2}\.\s+[A-Z])")
_PARAGRAPH_SEP = re.compile(r"\n\s*\n")
_SENTENCE_SEP = re.compile(r"(?<=[.!?])\s+(?=[A-Z\d])")

# Matches the pipe-delimited markdown table rows TextExtractor renders (both the PDF
# `_extract_pdf`/`page.find_tables()` path and the DOCX `_extract_docx` path use this exact
# `| cell | cell |` shape) — deliberately narrow/self-consistent rather than general-purpose
# table sniffing, since it only needs to recognize tables this codebase itself produced.
_TABLE_ROW_RE = re.compile(r"^\|.*\|\s*$")

# Common Indonesian official-title abbreviations that end in a period but are NOT sentence
# boundaries (e.g. "Dr. Iswanto, S.Pd, M.Kes") — found live in the corpus's e-signature
# blocks. Without this guard, the sentence splitter above fragments every signature line.
# The trailing `|[A-Za-z]` case guards single-letter section/list markers ("C.", "a.",
# "b.") — found live: without it, "C. Mekanisme Pendaftaran" and "b. Pendaftaran dilakukan"
# were being split right after the marker, severing every heading and list item from its
# own content (the one thing structure-aware chunking exists to prevent).
_ABBREV_GUARD_RE = re.compile(
    r"\b(Dr|Ir|Drs|Prof|No|Nomor|Jl|Kab|Kec|S\.Pd|S\.Kep|M\.Kes|dkk|dst|dsb|[A-Za-z])\.\s*$"
)


class ChunkingService:
    """Split text into overlapping chunks."""

    @staticmethod
    def tokenize(text: str) -> list[str]:
        """Simple tokenization by words."""
        return text.split()

    @staticmethod
    def _split_on(text: str, pattern: re.Pattern) -> list[str]:
        pieces = pattern.split(text)
        return [p for p in pieces if p and p.strip()]

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Sentence-boundary split with an abbreviation guard — imperfect (a truly robust
        splitter would need a full abbreviation dictionary) but strictly better than never
        checking for sentence boundaries at all, which is what chunk_text() below does."""
        parts = _SENTENCE_SEP.split(text)
        merged: list[str] = []
        for part in parts:
            if merged and _ABBREV_GUARD_RE.search(merged[-1]):
                merged[-1] = merged[-1] + " " + part
            else:
                merged.append(part)
        return [p for p in merged if p.strip()]

    @staticmethod
    def _recursive_split(text: str, max_tokens: int) -> list[str]:
        """Split `text` into pieces no larger than `max_tokens`, preferring the coarsest
        structural boundary that actually fits. Recurses to finer separators only for
        pieces still too big after the coarser split — this is what prevents ever cutting
        mid-sentence unless a single sentence alone exceeds the whole budget."""
        if len(ChunkingService.tokenize(text)) <= max_tokens:
            return [text]

        for splitter in (
            lambda t: ChunkingService._split_on(t, _NUMBERED_ITEM_SEP),
            lambda t: ChunkingService._split_on(t, _PARAGRAPH_SEP),
            ChunkingService._split_sentences,
        ):
            pieces = splitter(text)
            if len(pieces) > 1:
                result = []
                for piece in pieces:
                    result.extend(ChunkingService._recursive_split(piece, max_tokens))
                return result

        # A too-big piece that's (almost) entirely a rendered markdown table (see
        # _TABLE_ROW_RE) gets split by row instead of by raw word count, with the header +
        # separator row repeated in every split group — otherwise a forced split could sever
        # a header from its data rows, or cut a row in half, silently losing which column a
        # value belongs to.
        table_pieces = ChunkingService._split_table_by_rows(text, max_tokens)
        if table_pieces is not None:
            return table_pieces

        # Last resort: no structural or sentence boundary found in a too-big piece —
        # fall back to raw word-count slicing for this piece only, matching the old
        # chunk_text() behavior.
        words = text.split()
        return [" ".join(words[i:i + max_tokens]) for i in range(0, len(words), max_tokens)] or [text]

    @staticmethod
    def contains_table(text: str) -> bool:
        """Whether `text` contains at least one rendered markdown table row (see
        _TABLE_ROW_RE) — used by chunk_summary_service.py to decide whether a chunk needs the
        stricter table-preservation summary instructions and a larger output token budget."""
        return any(_TABLE_ROW_RE.match(line) for line in text.split("\n"))

    @staticmethod
    def _split_table_by_rows(text: str, max_tokens: int) -> list[str] | None:
        """If `text` is (almost entirely) a rendered markdown table, split it by row
        boundaries with the header+separator row repeated in every group. Returns None if
        `text` isn't recognizably table-shaped, so the caller falls back to word slicing."""
        lines = text.split("\n")
        table_line_count = sum(1 for line in lines if _TABLE_ROW_RE.match(line))
        non_blank_count = sum(1 for line in lines if line.strip())
        if non_blank_count == 0 or table_line_count / non_blank_count < 0.8:
            return None

        header_lines: list[str] = []
        row_lines: list[str] = []
        for line in lines:
            if _TABLE_ROW_RE.match(line):
                if len(header_lines) < 2:
                    header_lines.append(line)
                else:
                    row_lines.append(line)

        header_block = "\n".join(header_lines)
        header_tokens = len(ChunkingService.tokenize(header_block))

        groups: list[list[str]] = []
        current: list[str] = []
        current_tokens = header_tokens
        for row in row_lines:
            row_tokens = len(ChunkingService.tokenize(row))
            if current and current_tokens + row_tokens > max_tokens:
                groups.append(current)
                current = []
                current_tokens = header_tokens
            current.append(row)
            current_tokens += row_tokens
        if current:
            groups.append(current)

        if not groups:
            return [text]
        return [header_block + "\n" + "\n".join(group) for group in groups]

    @staticmethod
    def _detect_section(text: str) -> str | None:
        """Most recent lettered section heading ('C. Mekanisme Pendaftaran') appearing
        before/within this chunk's text, if any — populates DocumentChunk.section, which
        already flows into Chroma metadata and the multi-query reranker but has been an
        always-empty column until now (ingestion never detected headings before)."""
        matches = _SECTION_HEADING_RE.findall(text)
        return matches[0].strip() if matches else None

    @staticmethod
    def chunk_text_structured(
        text: str,
        chunk_size_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> list[dict]:
        """Structure-aware chunking: recursively split on section headings, numbered list
        items, paragraphs, then sentences — never mid-sentence unless a single sentence
        alone exceeds the token budget. Returns overlapping windows built from whichever
        structural pieces resulted, each tagged with its detected section heading (if any).

        Standard recursive-splitter approach (LangChain's RecursiveCharacterTextSplitter
        pattern) — found via 2026 RAG-chunking literature review to be the single highest-
        leverage, best-proven fix for the naive fixed-token chunk_text() below, which cuts
        mid-sentence and mixes unrelated structural units (legal citations, requirements,
        procedures) into the same chunk with no awareness of document structure at all.
        """
        chunk_size = chunk_size_tokens or (settings.chunk_size_tokens or 500)
        # `overlap_tokens or default` would silently discard an explicit 0 (falsy) and
        # substitute the ~100-token default instead -- found 2026-07-25 writing a section-
        # boundary regression test with overlap_tokens=0: the "reset current_parts on flush"
        # step became a no-op because the 100-token tail-carry re-absorbed the entire (tiny)
        # just-flushed chunk right back in, making every subsequent chunk grow cumulatively.
        overlap = overlap_tokens if overlap_tokens is not None else (settings.chunk_overlap_tokens or 100)

        pieces = ChunkingService._recursive_split(text, chunk_size)
        if not pieces:
            return []

        # Greedily merge adjacent structural pieces up to the token budget (mirrors
        # RecursiveCharacterTextSplitter's merge step) — a lettered section or a single
        # numbered point is often far smaller than chunk_size on its own, and merging
        # keeps chunk count sane instead of emitting dozens of tiny fragments.
        chunks: list[dict] = []
        current_parts: list[str] = []
        current_tokens = 0
        current_section: str | None = None

        def flush():
            if current_parts:
                text_out = " ".join(current_parts).strip()
                chunks.append({"text": text_out, "section": current_section})

        for piece in pieces:
            piece_tokens = len(ChunkingService.tokenize(piece))
            section = ChunkingService._detect_section(piece)
            # Found 2026-07-25 via gold-QA evaluation (Q002 "biaya pendaftaran" retrieval): the
            # greedy merge below used to stop ONLY on token budget, so several small lettered
            # sections (e.g. "B. Persyaratan Kelas Internasional", "C. Mekanisme Pendaftaran",
            # "F. Biaya") got silently folded into one chunk whenever each was individually
            # small — producing a summary/embedding that represents 4-5 unrelated topics at
            # once, which then loses the rerank to a more topically-focused chunk for any single
            # specific query. A detected section-heading change is now also a hard merge
            # boundary, same as the token budget, not instead of it.
            crosses_new_section = (
                current_parts and section is not None
                and current_section is not None and section != current_section
            )
            if current_parts and (current_tokens + piece_tokens > chunk_size or crosses_new_section):
                flush()
                # Overlap: carry the tail words of the previous chunk into the next one.
                tail_words = " ".join(current_parts).split()[-overlap:] if overlap else []
                current_parts = [" ".join(tail_words)] if tail_words else []
                current_tokens = len(tail_words)
                current_section = section
            if section:
                current_section = section
            current_parts.append(piece)
            current_tokens += piece_tokens

        flush()
        return [c for c in chunks if c["text"]]

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size_tokens: int | None = None,
        overlap_tokens: int | None = None,
    ) -> list[str]:
        """Split text into overlapping chunks by token count."""
        chunk_size = chunk_size_tokens or (settings.chunk_size_tokens or 500)
        overlap = overlap_tokens or (settings.chunk_overlap_tokens or 100)

        tokens = ChunkingService.tokenize(text)
        chunks = []
        
        if len(tokens) == 0:
            return chunks
        
        start = 0
        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk = " ".join(tokens[start:end])
            chunks.append(chunk)

            # Last chunk reached the end of the text — stop, otherwise
            # `end - overlap` would loop forever re-appending the tail.
            if end == len(tokens):
                break

            # Move start by (chunk_size - overlap), always making progress
            # even if overlap >= chunk_size.
            start = max(end - overlap, start + 1)

        return chunks

    @staticmethod
    def get_chunk_token_count(text: str) -> int:
        """Estimate token count (simple word count)."""
        return len(ChunkingService.tokenize(text))
