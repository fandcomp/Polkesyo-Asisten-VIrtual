# Campus Virtual Assistant — Poltekkes Kemenkes Yogyakarta

**Status:** Core chat pipeline (ACIF Gates 1–5, RAG, GraphRAG, OpenRouter), agentic orchestration
layer, and admin UI built and wired to the live API. Deployed to production (VPS + domain, Caddy
HTTPS). | **Version:** 0.1.0 | **Last Updated:** 2026-07-07

See [`IMPLEMENTATION.md`](./IMPLEMENTATION.md) for the detailed build status, the frontend↔backend
gap audit, and §6 for production deployment notes and incident history (two Chroma
event-loop-freeze incidents, 2026-07-06 and 2026-07-07 — read this before touching any Chroma call
site).

A production-ready virtual assistant for Poltekkes Kemenkes Yogyakarta campus information services, built with FastAPI, Next.js, OpenRouter LLM, PostgreSQL, Redis, Chroma (Vector RAG), Neo4j (GraphRAG), and ACIF (Adaptive Context Integrity Filtering).

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Node.js 22+

### 5-Minute Setup

```bash
# Copy environment file
cp .env.example .env

# Start dev stack
docker compose -f docker-compose.dev.yml up -d

# Wait ~30s for Neo4j initialization, then verify health
curl http://localhost:8000/health
```

Expected health response:
```json
{
  "status": "ok",
  "services": {
    "postgres": "ok",
    "redis": "ok",
    "chroma": "ok",
    "neo4j": "ok"
  }
}
```

### Access Services

| Service | URL | Purpose |
|---------|-----|---------|
| Backend API | http://localhost:8000 | FastAPI server |
| Frontend | http://localhost:3000 | Next.js UI |
| PostgreSQL | localhost:5433 | Database |
| Redis | localhost:6380 | Cache & rate limiting |
| Chroma | http://localhost:8001 | Vector database |
| Neo4j | http://localhost:7474 | Graph database |

## Architecture

**High-level flow:**

```
User Request
  ↓
Frontend Widget (Next.js/React)
  ↓
FastAPI Backend
  ↓
[ACIF Gate 1: Input Validation] → [Rate Limit Check]
  ↓
[Intent & Entity Extraction]
  ↓
[Vector RAG + GraphRAG Retrieval]
  ↓
[ACIF Gate 2-3: Context Scoring]
  ↓
[ACIF Gate 4: Prompt Boundary]
  ↓
OpenRouter LLM
  ↓
[ACIF Gate 5: Output Verification]
  ↓
Response to User
```

For detailed architecture, see `docs/public/architecture.md`.

## Build Roadmap

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Foundation (Docker, FastAPI skeleton) | ✅ Complete |
| 2 | Session and Consent | ✅ Complete |
| 3 | Dummy Chat Flow | ✅ Superseded by full pipeline |
| 4 | ACIF Gate 1 | ✅ Complete, unit tested |
| 5-9 | Document Workflow Foundation, Sync Worker, Manual Upload, Extraction/Chunking | ✅ Backend built, not verified live this session |
| 9 | Admin Chunk Management | ✅ Backend + frontend UI built, frontend still mock |
| 10-12 | Approved-only Vector Indexing, GraphRAG, Vector RAG Retrieval | ✅ Backend built |
| 13 | ACIF Gate 2 and Gate 3 | ✅ Complete, unit tested |
| 14 | OpenRouter | ✅ Complete |
| 15 | ACIF Gate 4 and Full Grounded Prompt | ✅ Complete, unit tested |
| 16 | Full Chat Flow | ✅ Complete |
| 17 | ACIF Gate 5 | ✅ Complete, unit tested |
| 18 | Redis Scaling (rate limit, queue, caching) | ✅ Complete |
| 19 | Evaluation | 📋 Not started |
| 20 | Staging/Production Deployment | ✅ Deployed to VPS + domain (Caddy HTTPS) — see IMPLEMENTATION.md §6 for incident history |
| — | Agentic Orchestration Architecture (CLAUDE.md §11A) | ✅ Built, verified live (see IMPLEMENTATION.md §5) |
| — | Frontend design system, theming, admin UI, monitoring dashboard | ✅ Built (see IMPLEMENTATION.md) |
| — | Frontend ↔ backend API wiring | ✅ Done — see IMPLEMENTATION.md §3-4 |

## Quick Commands

```bash
./scripts/dev-up.sh      # Start dev stack
./scripts/dev-down.sh    # Stop dev stack
curl http://localhost:8000/health  # Health check
```

## Documentation

See `CLAUDE.md` in repository root for complete project specification.
