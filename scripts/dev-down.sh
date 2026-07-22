#!/bin/bash
# Dev stack shutdown script

set -e

echo "Stopping Campus VA dev stack..."
docker compose -f docker-compose.dev.yml down

echo "✅ Dev stack stopped."
