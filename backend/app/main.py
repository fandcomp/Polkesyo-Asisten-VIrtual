import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes_health import router as health_router
from app.api.routes_sessions import router as sessions_router, consent_router
from app.api.routes_chat import router as chat_router
from app.api.routes_chat_agentic import router as chat_agentic_router
from app.api.routes_admin import router as admin_router
from app.api.routes_chunk_review import router as chunk_review_router
from app.api.routes_document_admin import router as document_admin_router
from app.api.routes_visual_chunks_admin import router as visual_chunks_admin_router
from app.api.routes_document_forms_admin import router as document_forms_admin_router
from app.api.routes_graph_admin import router as graph_admin_router
from app.api.routes_documents_public import router as documents_public_router
from app.api.routes_evaluation_admin import router as evaluation_admin_router
from app.api.routes_evaluation_public import router as evaluation_public_router
from app.core.config import settings
from app.core.security import require_admin_auth
from app.db.session import init_db

_is_production = settings.app_env == "production"

app = FastAPI(
    title="Campus Virtual Assistant API",
    description="Production-ready virtual assistant for Poltekkes Kemenkes Yogyakarta",
    version="0.1.0",
    docs_url=None if _is_production else "/docs",
    openapi_url=None if _is_production else "/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers. The four admin routers require HTTP Basic Auth (CLAUDE.md §26.2/§30) —
# applied at include_router() so the route files themselves don't need touching.
_admin_auth_dep = [Depends(require_admin_auth)]

app.include_router(health_router)
app.include_router(sessions_router)
app.include_router(consent_router)
app.include_router(chat_router)
app.include_router(chat_agentic_router)
app.include_router(documents_public_router)
app.include_router(evaluation_public_router)
app.include_router(admin_router, dependencies=_admin_auth_dep)
app.include_router(chunk_review_router, dependencies=_admin_auth_dep)
app.include_router(document_admin_router, dependencies=_admin_auth_dep)
app.include_router(visual_chunks_admin_router, dependencies=_admin_auth_dep)
app.include_router(document_forms_admin_router, dependencies=_admin_auth_dep)
app.include_router(graph_admin_router, dependencies=_admin_auth_dep)
app.include_router(evaluation_admin_router, dependencies=_admin_auth_dep)


_logger = logging.getLogger(__name__)
_allowed_origins = {origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a structured JSON error instead of a bare 500.

    CORS headers are set manually here: responses from exception handlers can bypass
    CORSMiddleware, and a 500 without Access-Control-Allow-Origin surfaces in the browser
    as an opaque "Failed to fetch" instead of a readable error body.
    """
    trace_id = str(uuid4())
    _logger.exception("Unhandled exception (trace_id=%s) on %s %s", trace_id, request.method, request.url.path)

    headers = {}
    origin = request.headers.get("origin")
    if origin and origin in _allowed_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"

    return JSONResponse(
        status_code=500,
        headers=headers,
        content={
            "trace_id": trace_id,
            "error_type": "internal_error",
            "message": "Terjadi gangguan pada layanan. Silakan coba lagi beberapa saat lagi.",
            "fallback": True,
        },
    )


@app.on_event("startup")
async def startup_event() -> None:
    """Initialize database tables and warm the embedding + reranker models on startup."""
    await init_db()

    # Load the sentence-transformers embedding model now (a few seconds from the
    # image-baked cache) instead of inside the first chat request's bounded 8s
    # Chroma call, where a cold load could blow the timeout.
    import asyncio

    from app.services.reranker_service import RerankerService
    from app.services.vector_index_service import VectorIndexService

    if settings.embedding_model_name.strip():
        await asyncio.to_thread(VectorIndexService.get_embedding_function)

    # Same cold-load-vs-request-timeout rationale as the embedding model above: found live
    # (2026-07-26) that a fresh process's first RerankerService.score_pairs call blew its
    # bounded timeout on model download/load, silently degrading that request to "no reranker
    # signal" instead of failing loudly — warm it here instead.
    if settings.reranker_enabled and settings.reranker_model_name.strip():
        await asyncio.to_thread(RerankerService.get_cross_encoder)


@app.get("/")
async def root():
    """Root endpoint — returns API metadata."""
    return {
        "name": "Campus Virtual Assistant",
        "version": "0.1.0",
        "env": settings.app_env,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=settings.app_env == "development",
    )
