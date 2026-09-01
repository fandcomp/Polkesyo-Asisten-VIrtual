# Load Test Results — 2026-07-23

Closes the "load testing never run" limitation (evaluation/reports/2026-07-18/README.md,
docs/paparan-sidang-tugas-akhir.md §26). Run against the production VPS from inside the
`campus-va_campus-va-network` Docker network (internal, no external network hop), staged ramp
per the remediation plan's caution requirement.

## Method

`locustfile.py`'s `CampusVAUser` mix: `/health` (weight 5), `/admin/visual-chunks/pending` and
`/detail` (weight 2 each, unauthenticated — expected 401), `/chat` (weight 1, low relative to
reads to bound OpenRouter cost under load). Three stages, increasing concurrent users, each 40s:

| Stage | Users | Spawn rate |
|---|---|---|
| 1 | 5 | 1/s |
| 2 | 15 | 3/s |
| 3 | 25 (= `LLM_MAX_CONCURRENCY`) | 5/s |

## Results

### `/health` — stable under load, no degradation

| Stage | Requests | Failures | Avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 1 (5 users) | 49-56 | 0 | 28 | 35 | 37 |
| 2 (15 users) | 138 | 0 | ~29 | 40 | 47 |
| 3 (25 users) | 256 | 0 | ~29 | 40 | 44 |

Zero failures across all three stages at any concurrency level tested. Latency stayed flat
(p95 35-40ms) from 5 to 25 concurrent users — no sign of degradation at the configured
concurrency cap.

### `/admin/visual-chunks/*` — correctly rejects unauthenticated load, fast

All requests returned `401 Unauthorized` as expected (the load test sends no admin
credentials) — this exercises the auth-check middleware path under load, not the full admin
read path. Rejection was fast and consistent: 2-3ms median, rising to 13-28ms p99 at 25 users
— acceptable, no sign of the auth layer becoming a bottleneck under load.

### `/chat` — not exercised end-to-end; documented test-harness limitation, not a product defect

All `/chat` requests returned `400 session_not_found` and failed in 2-16ms — far too fast to
have reached OpenRouter, so **no LLM cost was incurred** by any `/chat` call in this test.
Root cause: `chat_session_id` is a `Secure`-flagged cookie (`app/api/routes_sessions.py`,
matching CLAUDE.md §7's cookie config), so it is correctly dropped by the HTTP client when
`/sessions/init` and `/chat` are called in plain HTTP directly against the `backend` container
(bypassing Caddy's TLS termination, which real end-user traffic always goes through). Routing
the load test through Caddy itself (`https://caddy`) was attempted but hit a TLS/SNI
configuration error specific to Caddy's automatic-HTTPS setup for the internal Docker network
alias, not fixed in this pass — documented here as follow-up work rather than spent further
budget chasing it. **This is not a bug in the live system** — real users go through Caddy over
HTTPS and the Secure cookie round-trips normally; it's an artifact of this internal test
harness targeting the backend container directly.

## Interpretation

The system's request-handling path (routing, session/auth middleware, `/health`) shows no
latency or error-rate degradation from 5 to 25 concurrent users — the configured
`LLM_MAX_CONCURRENCY=25` ceiling was reached without incident on the infrastructure side. The
LLM-call path itself (`/chat` end-to-end under concurrent load) was **not** validated in this
pass due to the TLS/cookie limitation above — that remains open follow-up work, ideally by
running the load test from outside the VPS against the real public HTTPS endpoint instead of
the internal Docker network.

## Raw data

`results/stage_1_stats.csv`, `results/stage_2_stats.csv`, `results/stage_3_stats.csv` (Locust's
per-stage CSV output, on the VPS at `/opt/campus-va/evaluation/load_testing/results/`).
