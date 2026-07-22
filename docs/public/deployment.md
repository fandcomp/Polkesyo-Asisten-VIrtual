# Campus Virtual Assistant — Deployment Guide

## Development

```bash
cd campus-va
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
curl http://localhost:8000/health
```

Dev services: `backend` (uvicorn `--reload`, bind-mounts `backend/app` for hot-reload — no
rebuild needed for pure Python edits), `worker` (dedicated container for the 24h document sync
loop, kept separate from `backend` so local dev matches production topology), `frontend`
(Next.js, bind-mounts `frontend/src`), `postgres`, `redis`, `chroma`, `neo4j`. Dev exposes extra
host ports (5433, 6380, 8001, 7474, 7687) for local debugging with a DB client — production does
not.

## Production

```bash
# on the target host, campus-va/ checked out
cp .env.production .env   # fill in real secrets — see docs/public/api.md's auth note
docker compose -f docker-compose.prod.yml up -d --build
```

### Topology

```
Cloudflare (optional)
    ↓
Caddy (TLS termination, reverse proxy)
    ↓
[Frontend container]   [Backend containers — uvicorn --workers 4]
    ↓
Redis · PostgreSQL · Chroma · Neo4j
    ↓
OpenRouter (external LLM API)
```

`worker` runs the document-sync loop as a single dedicated instance, separate from the 4-worker
`backend` process group, so the recurring sync fires exactly once per interval rather than once
per uvicorn worker.

An `autoheal` sidecar (`willfarrell/autoheal`) watches containers labeled `autoheal=true` and
force-restarts them the moment Docker reports `unhealthy` — this closes a real gap where
`restart: always` never fires because a process is deadlocked (e.g. a wedged dependency call
freezing the event loop) but hasn't actually crashed. `backend` and `chroma` currently carry this
label; `chroma` additionally uses a raw TCP heartbeat healthcheck (the image ships no curl/wget)
because it has previously gone silently unresponsive while still accepting TCP connections.

### Resource/reliability settings worth knowing about

- `backend` runs with `ulimits.nofile: 65536` — a prior fd-leak incident (leaked Chroma client
  connections) exhausted the default 1024-file limit and turned every request on a saturated
  worker into an opaque failure.
- `chroma`'s data volume is mounted at `/data`, not `/chroma/chroma` — the image's actual default
  persistence path; mounting the wrong path silently discards the entire vector index on every
  container recreation.
- Postgres/Redis/Chroma/Neo4j publish no host ports in production — only reachable from other
  containers on the internal `campus-va-network` bridge network.

### Required production `.env` values

At minimum: `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`, `NEO4J_PASSWORD`,
`OPENROUTER_API_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` (bcrypt hash, never a plaintext
password — generate with `python -c "import bcrypt; print(bcrypt.hashpw(b'...', bcrypt.gensalt()).decode())"`),
`ALLOWED_ORIGINS`, `DOMAIN`, `API_DOMAIN`. See `.env.example` for the full configurable surface
(RAG/ACIF tuning, chunking, document sync, vision extraction, evaluation layer).

### Reverse proxy

Caddy is configured via `infra/Caddyfile` to route `/api/*` to the backend and everything else to
the frontend, with automatic TLS for the configured domains.

## Deployment quality gate

`GET /health` must report `postgres`, `redis`, `chroma`, and `neo4j` all `ok` before traffic is
considered safe to serve.

## What deployment does *not* do automatically

- Document sync never auto-approves or auto-indexes anything into the active knowledge base —
  every synced or uploaded document still requires admin chunk review (CLAUDE.md §21).
- There is currently no CI/CD pipeline; deploys are performed by building and starting the
  compose stack directly on the target host. Treat any deploy as a manual, reviewed operation.
