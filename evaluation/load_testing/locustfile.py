"""Load testing for Campus Virtual Assistant (CLAUDE.md §22, §28.4 load-readiness).

CampusVAUser mixes read-heavy admin/health traffic with occasional /chat calls (each a real,
billed OpenRouter call) — weighted low relative to health/admin reads to keep cost bounded
during a load test. Run staged (increasing -u user count across separate invocations) rather
than one large spike, per the 2026-07-23 remediation plan's caution requirement.
"""
from locust import HttpUser, task, between
import random


class CampusVAUser(HttpUser):
    """Simulates campus VA user behavior."""
    wait_time = between(1, 3)

    def on_start(self):
        self.doc_id = "doc-123"
        self.chunk_id = "vc-001"
        # Caddy's cert is self-signed/internal here — skip verification for the load test only.
        self.client.verify = False
        # /chat requires a chat_session_id cookie from /sessions/init first (routes_chat.py
        # returns 400 "session_not_found" otherwise) — HttpUser persists cookies per simulated
        # user, matching the real widget's session-init-then-chat flow (CLAUDE.md §7). The
        # cookie is Secure-flagged, so this must run over https (Caddy), not plain http
        # straight to the backend container, or the cookie is silently dropped.
        self.client.post("/sessions/init", name="POST /sessions/init")

    @task(5)
    def health_check(self):
        self.client.get("/health", name="GET /health")

    @task(2)
    def list_pending_chunks(self):
        self.client.get(
            f"/admin/visual-chunks/{self.doc_id}/pending",
            name="GET /admin/visual-chunks/pending",
        )

    @task(2)
    def get_chunk_detail(self):
        self.client.get(
            f"/admin/visual-chunks/{self.chunk_id}",
            name="GET /admin/visual-chunks/detail",
        )

    @task(1)
    def chat_query(self):
        """Real, billed OpenRouter call — kept at low task weight to bound cost under load."""
        questions = [
            "Apa saja syarat pendaftaran SPMB Jalur Mandiri?",
            "Kapan jadwal ujian CBT SPMB?",
            "Berapa biaya pendaftaran SPMB?",
        ]
        self.client.post(
            "/chat",
            json={"message": random.choice(questions)},
            name="POST /chat",
        )
