# Campus Virtual Assistant — Architecture Overview

## System Flow

```
User Request (Campus Information Query)
    ↓
[Frontend Widget — Next.js/React]
- Secure cookie-aware requests
- Consent banner
- Message input & display
    ↓
[FastAPI Backend Gateway]
- Request validation
- Session management
- Rate limiting
    ↓
[Chat Core Service]
- ACIF Gate 1: Input Validation
- Intent & Entity Extraction
- RAG Retrieval (Chroma + Neo4j)
- ACIF Gates 2-4: Context Scoring & Prompt Construction
- LLM Call (OpenRouter)
- ACIF Gate 5: Output Verification
- Citation Building
    ↓
[Response]
- Answer text (grounded in official sources)
- Source citations
- Status indicators
```

## Service Architecture

### Frontend
- **Technology:** Next.js 15, React 19, TypeScript
- **Responsibility:** Campus VA widget, session management, UI rendering
- **Port:** 3000 (dev)

### Backend
- **Technology:** FastAPI, Python 3.12+
- **Responsibility:** API orchestration, authentication, ACIF pipeline, LLM integration
- **Port:** 8000 (dev)
- **Key modules:**
  - `api/`: HTTP routes (health, chat, sessions, consent, admin)
  - `core/`: Config, logging, security, error handling
  - `services/`: Business logic (chat, intent, retrieval, ACIF)
  - `db/`: Database models, migrations (Alembic)
  - `schemas/`: Pydantic validation models

### Data Storage

| Service | Purpose | Dev Port | Production |
|---------|---------|----------|------------|
| PostgreSQL | Sessions, chat history, consent logs, evaluation data | 5433 | Managed RDS/Azure |
| Redis | Rate limiting, request queue, caching | 6380 | Managed ElastiCache |
| Chroma | Vector embeddings (Vector RAG) | 8001 | Managed or self-hosted |
| Neo4j | Knowledge graph (GraphRAG) | 7687 | Neo4j Aura or self-hosted |

## ACIF Pipeline (Phases 4-11)

Five sequential gates protect campus assistant answers:

1. **Gate 1: Input Intent Integrity** — Detect prompt injection, validate domain
2. **Gate 2: Retrieval Context Scoring** — Score chunks before LLM use  
3. **Gate 3: Graph-Document Consistency** — Verify retrieved chunks against graph
4. **Gate 4: Prompt Boundary** — Separate policy, input, context, and evidence
5. **Gate 5: Output Claim Verification** — Validate answer claims before response

See `CLAUDE.md §11` for full ACIF specification.

## RAG Pipeline (Phases 5-7)

Two complementary retrieval systems:

**Vector RAG (Chroma):**
- Semantic similarity over document chunks
- Recommended for question-answering
- Chunks: 400-600 tokens, 80-120 token overlap

**GraphRAG (Neo4j):**
- Structured entity relationships
- Recommended for navigation, policy compliance
- Entities: Programs, requirements, contacts, procedures

## Deployment Architecture (Phase 14)

```
Cloudflare (optional)
    ↓
Caddy/Nginx Reverse Proxy (TLS termination)
    ↓
[Backend Containers] (2+ replicas)
[Frontend Container]
    ↓
[Redis Cluster]
[PostgreSQL (managed)]
[Chroma (managed)]
[Neo4j (Aura or managed)]
    ↓
OpenRouter (external LLM API)
```

Recommended production server: 8 vCPU, 16 GB RAM, 160 GB disk.

## Security Model

- **User sessions:** Anonymous, UUID-based cookies
- **Consent tracking:** Essential-only vs. history & analytics
- **OpenRouter key:** Backend environment variable only
- **ACIF confidentiality:** Private implementation in `docs/private/acif/`
- **Rate limiting:** Redis-backed per-session, per-IP
- **Input validation:** Pydantic schemas + ACIF Gate 1

## Build Phases (from CLAUDE.md §36)

| Phase | Focus | When |
|-------|-------|------|
| 1 | Foundation (Docker, FastAPI skeleton) | ✅ Complete |
| 2 | Session & Consent Management | Phase 2 |
| 3 | Chat Endpoint & Frontend Widget | Phase 3 |
| 4-11 | ACIF Gates 1-5, RAG Integration | Phases 4-11 |
| 12 | Redis Scaling (rate limit, queue, cache) | Phase 12 |
| 13 | Evaluation Suite (test harness) | Phase 13 |
| 14 | Production Deployment | Phase 14 |

---

*Last Updated: 2026-06-30 | Status: Phase 1 Complete*
