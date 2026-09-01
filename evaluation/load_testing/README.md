# Load Testing

Closes the "load testing never run" limitation from `evaluation/reports/2026-07-18/README.md`
and `docs/paparan-sidang-tugas-akhir.md` §26. Previously lived outside `campus-va/` with no
requirements file or results — moved here 2026-07-23 as part of the evaluation remediation pass.

## Scenario

`locustfile.py`'s `CampusVAUser` mixes health checks and admin reads (unauthenticated —
expected to return 401/403 under load, still exercises routing/middleware) with a low-weight
`/chat` task. `/chat` makes a real, billed OpenRouter call per request, so its task weight is
kept low (1 out of 10) relative to health/read traffic to bound cost during a load test.

## Running (staged, per the remediation plan's caution requirement)

Run from inside the VPS against the internal Docker network (avoids an external network hop):

```bash
docker run --rm --network campus-va_campus-va-network \
  -v "$(pwd)/evaluation/load_testing:/mnt" \
  locustio/locust -f /mnt/locustfile.py --host=http://backend:8000 \
  --headless -u <USERS> -r <SPAWN_RATE> -t <DURATION> \
  --csv=/mnt/results/stage_<N>
```

Ramp `-u` across separate invocations (e.g. 5 -> 10 -> 15 users) rather than one large spike;
watch `/health` and error rates between stages; stop if error rates spike or the rate limiter
starts failing open (Redis down) instead of pushing through. Config guardrails to keep in mind
(`app/core/config.py`): `rate_limit_per_session_per_minute=10`, `rate_limit_per_ip_per_minute=60`,
`llm_max_concurrency=25`, `request_queue_max_size=500`. All simulated users share one source IP
(the load-test container), so the IP-level rate limit will engage well before 25 concurrent
users — that's expected, not a bug, and is itself part of what this test verifies.

Results (latency percentiles, failure counts) land in `results/stage_<N>_stats.csv` per stage.
