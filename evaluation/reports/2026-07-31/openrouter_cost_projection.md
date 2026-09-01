# OpenRouter Cost — Real Token Usage (historical) + Monthly Cost Projection (estimate)

**Per user instruction: this is a forward-looking PROJECTION, not a reconstruction of actual
historical dollar cost** (the `cost_usd`/`estimated_cost` columns in `openrouter_usage_logs` /
`chat_evaluation_logs` are confirmed broken — always logged as `0.0` — because OpenRouter's
`/chat/completions` response does not include a `total_cost` field by default; token counts
themselves are correctly logged and are used here as real, historical input to the projection).

## 1. Real historical token usage (2026-07-05 to 2026-07-27 08:28 UTC — account has been out of
   funds since, confirmed this session; 9,416 total OpenRouter calls across the whole system:
   real /chat generation + chunk summarization + eval-runner traffic)

| Model | Calls | Total Prompt Tokens | Total Completion Tokens | Avg Prompt/Call | Avg Completion/Call |
|---|---|---|---|---|---|
| google/gemini-2.5-flash | 4,788 | 14,271,594 | 633,386 | 2,980.7 | 132.3 |
| google/gemini-2.5-pro | 4,628 | 15,377,632 | 2,139,577 | 3,322.7 | 462.3 |
| **Total** | **9,416** | **29,649,226** | **2,772,963** | | |

Model split: 50.85% flash / 49.15% pro by call count.

## 2. OpenRouter published pricing (fetched live, 2026-07-31)

| Model | Input ($/1M tokens) | Output ($/1M tokens) |
|---|---|---|
| google/gemini-2.5-pro | $1.25 | $10.00 |
| google/gemini-2.5-flash | $0.30 | $2.50 |

Source: openrouter.ai/google/gemini-2.5-pro and openrouter.ai/google/gemini-2.5-flash (list
prices; OpenRouter notes actual paid cost can be 60-80% lower with prompt caching, which this
projection does NOT assume — it is a conservative/upper-bound estimate).

## 3. Weighted average cost per call (using real observed token averages above)

- flash: (2,980.7/1e6 × $0.30) + (132.3/1e6 × $2.50) = **$0.001225/call**
- pro: (3,322.7/1e6 × $1.25) + (462.3/1e6 × $10.00) = **$0.008776/call**
- Weighted (50.85% flash / 49.15% pro): **≈ $0.004936/call**

## 4. Monthly cost PROJECTION scenarios (estimate, not actual spend)

| Scenario | Assumption | Queries/month | Projected Monthly Cost |
|---|---|---|---|
| A — historical rate extrapolated | Same call rate/mix as 2026-07-05→27 (428 calls/day observed, includes eval-run traffic, not just organic) | ~12,840 | **≈ $63.40** |
| B — small pilot | 100 active users × 2 queries/day | 6,000 | **≈ $29.62** |
| C — CLAUDE.md target scale ("hundreds of users") | 300 active users × 3 queries/day | 27,000 | **≈ $133.28** |
| D — upper-bound target scale | 500 active users × 5 queries/day | 75,000 | **≈ $370.23** |

Configured safety guard on the VPS: `OPENROUTER_DAILY_BUDGET_USD=10`,
`OPENROUTER_MONTHLY_BUDGET_USD=150` (per `.env`) — Scenario C sits above the configured monthly
guard, and Scenario D substantially above it; note this guard is currently non-functional in
practice because of the `cost_usd`-always-0 bug (§ raw_vps/postgres_aggregates.txt item 12) — it
would not actually stop spend at these projected volumes today.

## Caveats

- These are **estimates**, built from real historical token-per-call averages × published
  list pricing × assumed future volume — not a reconstruction of what was actually billed
  historically (which cannot be recovered due to the cost-logging bug).
- Scenario A's historical rate mixes real chat traffic with heavy evaluation-ablation-sweep
  traffic from the 2026-07-24 to 07-27 sessions — it is not a clean "organic users only" number.
- Real per-token pricing changes over time; treat this as a 2026-07-31 snapshot.
