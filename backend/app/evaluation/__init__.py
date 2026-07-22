"""Evaluation Layer Phase 3 — gold QA dataset, metrics, and the standalone evaluation runner.

Lives under app/evaluation/ (not a top-level backend/evaluation/ or the pre-existing, unused
campus-va/evaluation/) because only backend/app is baked into the production Docker image and
bind-mounted in dev — see IMPLEMENTATION.md for the full reasoning.
"""
