# Campus Virtual Assistant — API Overview

High-level reference for the FastAPI backend's HTTP surface. This describes request/response
shape and purpose only — internal ACIF scoring formulas, thresholds, and prompt construction
details are documented privately (see `docs/private/acif/`), not here.

All endpoints are served under the backend's base URL (`http://localhost:8000` in dev). Admin
endpoints require HTTP Basic Auth (`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`) and are never exposed
without it — see `docs/public/deployment.md` for how credentials are provisioned.

## Health

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service health for Postgres, Redis, Chroma, Neo4j — used by container healthchecks and uptime monitoring. |

## Session & Consent

| Method | Path | Purpose |
|---|---|---|
| POST | `/sessions/init` | Create or resume an anonymous session; sets the `chat_session_id` secure cookie. |
| POST | `/consent/` | Record the visitor's cookie/data-use consent choice (`essential_only` or `history_and_analytics`). |
| GET | `/consent/{session_id}` | Look up the recorded consent choice for a session. |

## Chat

| Method | Path | Purpose |
|---|---|---|
| POST | `/chat` | The original single-pipeline chat endpoint (session → consent → rate limit → ACIF Gates 1-5 → RAG/GraphRAG → OpenRouter → citation). Fully supported, not deprecated. |
| POST | `/api/chat/agentic` | Additive parallel entrypoint running the same underlying logic through the named-agent orchestration layer (CLAUDE.md §11A). Produces functionally identical grounded, cited answers to `/chat`. |
| GET | `/api/agent-runs` *(admin)* | List per-agent execution log rows (`agent_run_logs`) for the agentic pipeline. |
| GET | `/api/agent-runs/{run_id}` *(admin)* | Detail view of a single agent run, including input/output summaries and latency. |

Both chat endpoints return an `answer`, a `sources[]` citation list, a `status` (e.g. `answered`,
`out_of_domain`, `insufficient_context`, `rejected_by_input_filter`, `fallback_enforced`), and the
active `session_id`.

## Public Documents

| Method | Path | Purpose |
|---|---|---|
| GET | `/documents/{document_id}/download` | Serve an approved, active document's raw file for public download (e.g. an official PDF guideline). |

## Admin — Document Sync & Upload

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/documents/sync` | Manually trigger the official-source document sync worker. |
| POST | `/admin/documents/check-updates` | Check the official listing for new/changed documents without downloading. |
| GET | `/admin/documents/sources` | List configured document sources (manual upload, official sync URL) and their status. |
| POST | `/admin/documents/upload` | Manual admin document upload (validates type/size, stores as `pending_review`, never auto-approved). |
| POST | `/admin/ingestion/ingest-document/{version_id}` | Run extract → chunk → summarize for a document version. |
| GET | `/admin/documents` | List documents with status/chunk-count filters. |
| GET | `/admin/documents/{document_id}` | Single document detail. |
| GET | `/admin/documents/{document_id}/chunks` | Chunks for a document, for the review UI. |
| PATCH | `/admin/documents/{document_id}/status` | Change a document's lifecycle status. |
| GET | `/admin/stats/summary` | Aggregate document/chunk counts for the admin dashboard. |

## Admin — Chunk Review & Approval

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/chunks/pending-review` | List text chunks awaiting admin review. |
| PATCH | `/admin/chunks/{chunk_id}/summary` | Edit the admin-facing chunk summary before approval. |
| POST | `/admin/chunks/{chunk_id}/approve` | Approve a chunk (also supports reject/needs-revision decisions in the same endpoint). |
| POST | `/admin/chunks/bulk-approve` | Approve multiple reviewed chunks at once (explicit confirmation required in the UI). |
| POST | `/admin/documents/{document_id}/approve-chunk/{chunk_id}` | Per-document chunk approval variant. |
| POST | `/admin/documents/{document_id}/reject-chunk/{chunk_id}` | Per-document chunk rejection variant. |

## Admin — Visual Chunks (CLAUDE.md §38)

| Method | Path | Purpose |
|---|---|---|
| GET | `/admin/visual-chunks/{document_id}/pending` | List image/diagram/table chunks awaiting review for a document. |
| GET | `/admin/visual-chunks/{chunk_id}/image` | Serve the original extracted image artifact. |
| GET | `/admin/visual-chunks/{chunk_id}` | Visual chunk detail (vision description draft, visible text draft, risk flags). |
| POST | `/admin/visual-chunks/{chunk_id}/approve` | Approve a visual chunk for indexing. |
| POST | `/admin/visual-chunks/{chunk_id}/reject` | Reject a visual chunk. |
| POST | `/admin/visual-chunks/{chunk_id}/needs-revision` | Send a visual chunk back for revision. |

## Admin — Indexing & Knowledge Graph

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/indexing/run` | Index newly approved chunks into the active Chroma collection. |
| POST | `/admin/indexing/rebuild` | Rebuild the entire active Chroma collection (e.g. after an embedding model change). |
| POST | `/admin/graph/index-document` | Ingest a document's approved entities/relations into Neo4j. |
| GET | `/api/admin/kg/documents/{document_id}` | Per-document knowledge-graph view. |
| GET | `/api/admin/kg/graph` | Global knowledge-graph view for the admin Knowledge Graph Viewer. |

## Admin — Evaluation

All under `/api/admin/evaluation`. Covers technical/ACIF observability logs (`chat-logs`,
`retrieval-logs`, `citation-logs`, `acif-traces`, `graph-consistency`), CSV export endpoints for
each log type plus a combined report, gold-QA evaluation run management (`runs`, `results`,
`compare`, `gold-qa-dataset`), usability results (`asq-summary`, `asq-responses`, `sus-summary`,
`sus-responses`), an aggregate `overview`, and evaluation-scenario management (`scenarios` —
GET/POST/PATCH; no DELETE, scenarios are soft-deactivated only since real participant responses
reference them by ID).

## Public Evaluation Flow

Under `/api/evaluation`, rate-limited per IP:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/evaluation/scenarios` | List active scenarios for a usability-study participant. |
| POST | `/api/evaluation/asq` | Submit an After-Scenario Questionnaire response. |
| POST | `/api/evaluation/sus` | Submit a System Usability Scale response. |

## Response Conventions

- Every chat response carries a `trace_id` for cross-referencing admin observability tables.
- Error responses are sanitized — no stack traces, internal prompts, or credentials are ever
  returned to the client (CLAUDE.md §17, §26).
- Rate-limited requests receive a controlled "please wait" response rather than a raw 429 with
  no explanation, except on evaluation/admin-auth endpoints where a standard HTTP status is used.
