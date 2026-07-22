"""ACIF Gate 3: Graph-Document Consistency Check.

Consistency semantics (CLAUDE.md §11.4): a chunk is INCONSISTENT when it discusses a
*different* entity of the same kind than the graph evidence for this query — e.g. the
user asks about Jalur Mandiri (graph evidence: JalurPendaftaran = "Jalur Mandiri") and
the chunk only discusses Jalur Prestasi. A chunk that simply doesn't mention any graph
entity is NOT contradicted — it merely lacks graph corroboration and proceeds with
caution (it earns no no_contradiction credit in Gate 2 and no graph boost in reranking).
Treating "no mention" as contradiction rejected approved, on-topic chunks whenever the
graph was sparsely populated, which is a false-fallback bug, not a safety property.
"""


class GraphDocumentConsistency:
    """Check if retrieved chunks match knowledge graph evidence."""

    # Entity types where discussing a different value genuinely signals the chunk is
    # about another program/pathway (CLAUDE.md §11.4's examples). Broad types like
    # Persyaratan/Jadwal are not identity-bearing — many legitimately co-occur.
    _IDENTITY_TYPES = {"ProgramStudi", "JalurPendaftaran"}

    @staticmethod
    async def check_consistency(
        chunk: dict,
        graph_entities: list[dict],
    ) -> dict:
        """Check chunk text against graph evidence for this query."""
        chunk_text = chunk.get("content", "").lower()

        if not graph_entities:
            # No graph evidence available
            return {
                "chunk_id": chunk.get("chunk_id"),
                "consistency_score": 0.5,
                "decision": "proceed_with_caution",
                "note": "No graph evidence available",
            }

        # Count entity mentions in chunk, deduped by name (case-insensitive; an entity with
        # no name at all is kept as a single unmatchable "" placeholder, same as before).
        # graph_entities can contain the same entity multiple times — once per relation it
        # participates in — so counting raw list length as the denominator would double-
        # (or 4x-) penalize a chunk for relations it has nothing to do with.
        unique_entity_names = {entity.get("entity_name", "").lower() for entity in graph_entities}
        total_entities = len(unique_entity_names)
        entity_mentions = sum(1 for name in unique_entity_names if name and name in chunk_text)

        consistency_score = (entity_mentions / total_entities) if total_entities > 0 else 0.5

        if consistency_score >= 0.7:
            decision = "highly_consistent"
        elif consistency_score >= 0.4:
            decision = "consistent"
        elif entity_mentions > 0:
            # A broad intent-level graph query (e.g. "jalur") can legitimately return entities
            # spanning several jalur/programs at once. A single chunk is only ever about one
            # of them, so requiring it to cover most of the returned set would reject correct,
            # on-topic chunks — what matters is that it aligns with *some* real graph evidence.
            decision = "consistent"
        elif GraphDocumentConsistency._conflicts_with_graph(chunk_text, graph_entities):
            # Zero mentions AND the chunk identifies itself as being about a different
            # program/jalur than the graph evidence — the §11.4 inconsistent case.
            decision = "inconsistent_flag"
        else:
            # Zero mentions, no conflicting identity — uncorroborated, not contradicted.
            decision = "proceed_with_caution"

        return {
            "chunk_id": chunk.get("chunk_id"),
            "consistency_score": consistency_score,
            "decision": decision,
            "entity_matches": entity_mentions,
            "total_entities": total_entities,
        }

    @staticmethod
    def _conflicts_with_graph(chunk_text: str, graph_entities: list[dict]) -> bool:
        """True when the chunk names a different identity-bearing entity (program/jalur)
        than every graph-evidence entity of that same type.

        Uses the shared GraphService.extract_entities keyword extractor (the same one
        graph ingestion and the admin review UI use) so "what counts as an entity" has
        exactly one definition in the codebase.
        """
        from app.services.graph_service import GraphService

        graph_by_type: dict[str, set[str]] = {}
        for entity in graph_entities:
            entity_type = entity.get("entity_type") or ""
            name = (entity.get("entity_name") or "").lower()
            if entity_type in GraphDocumentConsistency._IDENTITY_TYPES and name:
                graph_by_type.setdefault(entity_type, set()).add(name)

        if not graph_by_type:
            return False

        try:
            chunk_entities = GraphService.extract_entities(chunk_text)
        except Exception:
            return False  # extraction failure must not reject a chunk

        for entity_type, graph_names in graph_by_type.items():
            chunk_names = {
                name.lower() for etype, name in chunk_entities if etype == entity_type
            }
            if chunk_names and not (chunk_names & graph_names):
                return True
        return False
