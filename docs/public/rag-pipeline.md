# Campus Virtual Assistant — RAG & GraphRAG Pipeline

## Overview

Every campus-related answer is grounded in retrieved official context before it reaches the LLM.
Two complementary retrieval systems feed that context, and every retrieved item is scored for
context integrity before it's allowed into the prompt — internal scoring formulas and thresholds
are documented privately (see `docs/private/acif/`); this document covers the retrieval mechanism
itself at a methodological level.

## Query Understanding

Before retrieval runs, the user's question passes through a query-understanding stage:
normalization, acronym expansion (e.g. institution-specific abbreviations), synonym mapping,
intent-aware query rewriting, and — for multi-turn conversations — resolving references against
recent conversation context. This produces the actual query(ies) sent to retrieval, not the raw
user text verbatim.

## Vector RAG (Chroma)

Semantic similarity search over approved, active document chunks using a multilingual sentence
embedding model (tuned for Indonesian, since the source corpus and most user questions are in
Indonesian). Retrieval uses a query-rewriting/multi-query strategy — several query variants
(covering rephrasing and intent-specific expansions such as fee/schedule figure-seeking) are
searched and the results reranked and merged, rather than a single raw-text embedding lookup.
Reranking applies intent-aware bonuses (e.g. preferring chunks from the document type that
actually matches the question's intent, and chunks containing the literal figures/dates a
figure-seeking question needs) on top of raw similarity.

Chunking: documents are split into structure-aware chunks (section headings, numbered items,
paragraphs, then sentences — never mid-sentence) of roughly 400-600 tokens with 80-120 token
overlap, following CLAUDE.md §20's guidance rather than fixed-size splitting.

## GraphRAG (Neo4j)

Structured institutional knowledge — programs, admission pathways, requirements, schedules, fees,
service units, contacts, regulations — modeled as entities and relationships, ingested only from
admin-approved document content. Graph evidence is used both directly (as a structured fact
source in the final prompt) and as a consistency check against vector-retrieved chunks: a chunk
whose apparent subject conflicts with graph evidence for the same entities is down-weighted or
rejected before ever reaching the LLM.

## Context Integrity Before Generation

All candidate context — vector chunks and graph evidence alike — passes through context-integrity
scoring and a graph-document consistency check before prompt construction. Only context that
survives this filtering is included; rejected chunks are never sent to the LLM, and the assistant
falls back to an explicit "not available in current official sources" response rather than
guessing when nothing sufficient survives.

## Known Limitation — Chunk ID Stability

Document chunk IDs are deterministic based on `(document version, chunk position, chunk kind)`,
so re-ingesting an *unchanged* document version reproduces the same chunk IDs (this matters for
anything that references a specific chunk across time, such as evaluation ground truth). This
does **not** survive a document or document version being deleted and recreated — a genuinely new
version always gets new chunk IDs, which is expected since its content may differ.

## Retrieval Tuning Surface

Retrieval breadth (`top_k`), similarity threshold, and context-token budget are environment
configurable (see `.env.example`) rather than hardcoded, so they can be tuned per deployment
without a code change — see CLAUDE.md §15/§25 for the full parameter list and recommended
defaults.
