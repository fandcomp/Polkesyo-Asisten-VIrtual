#!/bin/bash
# Database migration script

set -e

cd backend
alembic upgrade head
echo "✅ Database migrations complete."
