from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    app_port: int = 8000

    # Database
    database_url: str = "postgresql+asyncpg://assistant_user:assistant_password@postgres:5432/assistant_db"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Vector DB (Chroma)
    chroma_host: str = "chroma"
    chroma_port: int = 8000

    # Graph DB (Neo4j)
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "assistant_neo4j_password"

    # OpenRouter (configured in Phase 8+)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_primary_model: str = "google/gemini-2.5-pro"
    openrouter_fallback_model: str = "google/gemini-2.5-flash"
    # Vision-LLM model for image/table description (ingestion/vision_description_service.py).
    # "google/gemini-2.5-vision-flash" (the old hardcoded fallback) is not a real OpenRouter
    # model slug — this is the correct one, matching what production actually uses.
    openrouter_vision_model: str = "google/gemini-2.5-flash"
    vision_extraction_enabled: bool = True

    # Session & Consent
    session_cookie_name: str = "chat_session_id"
    consent_cookie_name: str = "chat_consent"

    # Admin auth (HTTP Basic, protects all /admin/* routes + agent-run introspection)
    admin_username: str = "admin"
    admin_password_hash: str = ""

    # Second admin account (reviewer role) — same auth mechanism, but restricted to a fixed
    # subset of Evaluation sub-tabs (see security.py's EVALUATION_TABS_SECOND_ADMIN). Empty =
    # disabled, matching admin_password_hash's convention.
    second_admin_username: str = ""
    second_admin_password_hash: str = ""

    # CORS
    allowed_origins: str = "http://localhost:3000"

    # Rate Limiting
    rate_limit_per_session_per_minute: int = 10
    rate_limit_per_ip_per_minute: int = 60
    max_llm_calls_per_session_per_day: int = 50

    # Request Queue
    request_queue_max_size: int = 500
    llm_max_concurrency: int = 25

    # Embedding model for Chroma (sentence-transformers name). Empty = Chroma's default
    # (English all-MiniLM-L6-v2). Changing this requires REBUILDING the active collection —
    # embeddings from different models are not comparable even at equal dimensionality.
    embedding_model_name: str = ""

    # RAG
    rag_top_k: int = 5
    # Broader recall for short/low-confidence queries (Query Understanding Layer)
    rag_top_k_broad: int = 8
    graph_top_k: int = 5
    rag_similarity_threshold: float = 0.35  # superseded by MultiQueryRetriever reranking
    max_context_chunks: int = 5
    max_context_tokens: int = 4000

    # LLM Generation
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2000

    # ACIF
    acif_enabled: bool = True
    acif_strict_mode: bool = True
    acif_input_reject_threshold: float = 0.25
    acif_input_caution_threshold: float = 0.10
    acif_context_keep_threshold: float = 0.75
    acif_context_verify_threshold: float = 0.50
    acif_context_min_threshold: float = 0.35
    # Bounded recall aid for short acronym queries: added in Gate 2 only when an exact
    # detected domain term matched an APPROVED chunk. Not a threshold change.
    acif_context_exact_term_bonus: float = 0.05
    # Same bounded-bonus pattern, for a chunk whose detected section heading (populated by
    # the structure-aware chunker) shares vocabulary with the query.
    acif_context_section_match_bonus: float = 0.05
    acif_max_selected_contexts: int = 3
    acif_graph_support_min: float = 0.40
    acif_max_prompt_input_tokens: int = 4500
    acif_grounding_verified_threshold: float = 0.80
    acif_grounding_fallback_threshold: float = 0.60
    acif_require_citation: bool = True
    # CLAUDE.md §11.6 "Regenerate with stricter prompt if allowed by configuration":
    # when Gate 5 finds unsupported critical claims but the answer is otherwise strongly
    # grounded (confidence >= acif_grounding_verified_threshold), regenerate ONCE with an
    # explicit instruction to drop the failing claims, then re-verify. Never bypasses
    # verification — a still-failing regeneration falls back exactly as before.
    acif_regenerate_on_unsupported: bool = True

    # OpenRouter Budget
    openrouter_daily_budget_usd: float = 10.0
    openrouter_monthly_budget_usd: float = 150.0

    # Document Management (Phase 9+)
    max_upload_file_size_mb: int = 25
    allowed_upload_extensions: str = "pdf,docx,html"
    raw_document_storage_path: str = "data/raw"
    processed_document_storage_path: str = "data/processed"

    # Chunking (Phase 11+)
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 100

    # Chunk summary drafts (Phase 8)
    chunk_summary_enabled: bool = True
    # flash-lite followed the verbatim-preservation and language-match instructions
    # inconsistently in testing; flash is a small cost increase for materially better
    # instruction-following on a step that directly affects retrieval and grounding quality.
    chunk_summary_model: str = "google/gemini-2.5-flash"
    chunk_summary_max_tokens: int = 400

    # ACIF Gate 5 LLM-based claim verification (falls back to the regex heuristic on any error)
    openrouter_verification_model: str = "google/gemini-2.5-flash"

    # Document sync / DocumentMonitorAgent (CLAUDE.md §11A.3/§21.2)
    document_sync_enabled: bool = True
    document_sync_source_url: str = (
        "https://sipenmaru.poltekkesjogja.ac.id/index.php?mod=login_default&sub=filePanduan&act=view&typ=html"
    )
    document_sync_interval_hours: int = 24
    document_sync_timeout_seconds: int = 30
    document_sync_user_agent: str = "campus-virtual-assistant-sync/1.0"

    # Evaluation Layer (Phase 1 — technical/ACIF observability logging on the /chat pipeline)
    evaluation_enabled: bool = True
    evaluation_logging_enabled: bool = True
    evaluation_mode_public: bool = False
    evaluation_log_full_answer: bool = True
    evaluation_log_full_context: bool = False
    evaluation_retention_days: int = 90

    # Evaluation Layer Phase 2 — admin observability UI + CSV export
    evaluation_ui_enabled: bool = True
    evaluation_export_enabled: bool = True
    evaluation_export_max_rows: int = 50000

    # Evaluation Layer Phase 3 — gold QA dataset runner
    evaluation_runner_enabled: bool = True
    evaluation_runner_concurrency: int = 3
    evaluation_runner_timeout_seconds: int = 90
    evaluation_llm_judge_enabled: bool = False

    # Evaluation Layer Phase 4 — ASQ/SUS usability evaluation
    asq_enabled: bool = True
    sus_enabled: bool = True

    # ACIF Observability (safe, per-gate audit trail — never raw prompts/formulas/secrets)
    acif_observability_enabled: bool = True
    acif_admin_trace_enabled: bool = True
    acif_show_internal_formula: bool = False
    acif_show_raw_prompt: bool = False


settings = Settings()
