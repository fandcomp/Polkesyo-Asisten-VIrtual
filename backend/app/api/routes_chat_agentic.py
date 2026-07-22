"""Agentic chat entrypoint + agent run inspection (CLAUDE.md §11A)."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator_agent import OrchestratorAgent
from app.core.errors import SessionNotFoundError
from app.core.security import require_admin_auth
from app.db.models import AgentRunLog
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ErrorResponse

router = APIRouter(prefix="/api", tags=["agentic"])


@router.post("/chat/agentic", response_model=ChatResponse)
async def chat_agentic(
    request: ChatRequest,
    chat_session_id: UUID | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
):
    """Process user message through the Agentic Orchestration Architecture (CLAUDE.md §11A).

    Additive to POST /chat — same ACIF/grounding/citation guarantees, dispatched through named
    agents instead of one linear function.
    """
    if not chat_session_id:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                trace_id=str(uuid4()),
                error_type="session_not_found",
                message="Sesi Anda belum dimulai. Muat ulang halaman untuk memulai sesi baru.",
            ).model_dump(),
        )

    try:
        return await OrchestratorAgent.handle_chat_request(
            db=db,
            session_id=chat_session_id,
            message=request.message,
            metadata=request.metadata,
        )
    except SessionNotFoundError:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                trace_id=str(uuid4()),
                error_type="session_not_found",
                message=(
                    "Sesi Anda tidak ditemukan atau sudah berakhir. "
                    "Muat ulang halaman untuk memulai sesi baru."
                ),
            ).model_dump(),
        )


@router.get("/agent-runs", dependencies=[Depends(require_admin_auth)])
async def list_agent_runs(
    limit: int = 50,
    agent_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List recent agent run log entries (CLAUDE.md §11A.5), newest first."""
    stmt = select(AgentRunLog).order_by(AgentRunLog.created_at.desc()).limit(min(limit, 200))
    if agent_name:
        stmt = stmt.where(AgentRunLog.agent_name == agent_name)
    result = await db.execute(stmt)
    runs = result.scalars().all()
    return {
        "total": len(runs),
        "runs": [_serialize_run(r) for r in runs],
    }


@router.get("/agent-runs/{run_id}", dependencies=[Depends(require_admin_auth)])
async def get_agent_run(run_id: UUID, db: AsyncSession = Depends(get_db)):
    """Get a single agent run log entry by id."""
    stmt = select(AgentRunLog).where(AgentRunLog.id == run_id)
    result = await db.execute(stmt)
    run = result.scalars().first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _serialize_run(run)


def _serialize_run(run: AgentRunLog) -> dict:
    return {
        "id": str(run.id),
        "agent_name": run.agent_name,
        "task_type": run.task_type,
        "status": run.status,
        "latency_ms": run.latency_ms,
        "error_message": run.error_message,
        "input_summary": run.input_summary,
        "output_summary": run.output_summary,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
