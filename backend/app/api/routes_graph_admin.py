"""Admin routes for reading the Knowledge Graph (CLAUDE.md §11A.4).

Read-only — Neo4j stays the only store for graph provenance/status (no kg_nodes/kg_edges
mirror in Postgres). These endpoints exist so the admin Knowledge Graph panel can render
what's actually in the graph, instead of only ever writing to it via
POST /admin/graph/index-document with no way to see the result.
"""
from uuid import UUID

from fastapi import APIRouter

from app.services.graph_service import GraphService

router = APIRouter(prefix="/api/admin/kg", tags=["admin-knowledge-graph"])


@router.get("/documents/{document_id}")
async def get_document_graph(document_id: UUID):
    """Nodes + edges for one document's indexed knowledge-graph evidence."""
    return await GraphService.get_graph_for_document(str(document_id))


@router.get("/graph")
async def get_global_graph(limit: int = 150):
    """Capped global snapshot of the knowledge graph across all documents."""
    return await GraphService.get_graph_global(limit=limit)
