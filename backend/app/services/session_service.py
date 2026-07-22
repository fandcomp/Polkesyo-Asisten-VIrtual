"""Session and consent management service."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Session, ConsentLog
from app.schemas.session import ConsentCreate


class SessionService:
    """Manage user sessions."""

    @staticmethod
    async def create_session(db: AsyncSession, user_agent_hash: str | None = None) -> Session:
        """Create a new anonymous session."""
        session = Session(id=uuid4(), user_agent_hash=user_agent_hash)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    @staticmethod
    async def get_session(db: AsyncSession, session_id: UUID) -> Session | None:
        """Get session by ID."""
        stmt = select(Session).where(Session.id == session_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def update_last_active(db: AsyncSession, session_id: UUID) -> bool:
        """Update last active timestamp for a session."""
        session = await SessionService.get_session(db, session_id)
        if not session:
            return False
        session.last_active_at = datetime.utcnow()
        await db.commit()
        return True

    @staticmethod
    async def get_or_create_session(
        db: AsyncSession,
        session_id: UUID | None = None,
        user_agent_hash: str | None = None
    ) -> Session:
        """Get existing session or create new one."""
        if session_id:
            session = await SessionService.get_session(db, session_id)
            if session:
                await SessionService.update_last_active(db, session_id)
                return session
        return await SessionService.create_session(db, user_agent_hash)


class ConsentService:
    """Manage user consent tracking."""

    @staticmethod
    async def set_consent(
        db: AsyncSession,
        session_id: UUID,
        consent_value: str,
        source: str | None = None
    ) -> ConsentLog:
        """Record consent choice for a session."""
        consent_log = ConsentLog(
            session_id=session_id,
            consent_value=consent_value,
            source=source
        )
        db.add(consent_log)
        await db.commit()
        await db.refresh(consent_log)
        return consent_log

    @staticmethod
    async def get_latest_consent(db: AsyncSession, session_id: UUID) -> ConsentLog | None:
        """Get most recent consent record for session."""
        stmt = (
            select(ConsentLog)
            .where(ConsentLog.session_id == session_id)
            .order_by(ConsentLog.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def has_consent(db: AsyncSession, session_id: UUID) -> bool:
        """Check if session has provided consent."""
        consent = await ConsentService.get_latest_consent(db, session_id)
        return consent is not None