#!/bin/bash
# Dev stack startup script

set -e

echo "Starting Campus VA dev stack..."
docker compose -f docker-compose.dev.yml up -d

echo "Waiting for services to initialize (30 seconds)..."
sleep 30

echo ""
echo "✅ Dev stack started!"
echo ""
echo "Available services:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  Postgres: localhost:5433"
echo "  Redis:    localhost:6380"
echo "  Chroma:   http://localhost:8001"
echo "  Neo4j:    http://localhost:7474"
echo ""
echo "Check health:"
echo "  curl http://localhost:8000/health"
