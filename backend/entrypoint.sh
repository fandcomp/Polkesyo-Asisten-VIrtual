#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
until pg_isready -h postgres -U assistant_user -d assistant_db; do
  sleep 1
done
echo "PostgreSQL is ready"

echo "Running migrations..."
cd /app
python -c "
import asyncio
import sys
sys.path.insert(0, '/app')
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.config import settings
from app.db.models import Base

async def init_db():
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print('Database tables created')

asyncio.run(init_db())
"

echo "Starting uvicorn..."
exec "$@"
