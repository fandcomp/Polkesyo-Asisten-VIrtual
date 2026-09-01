"""Query Neo4j for structured knowledge."""
from neo4j import AsyncGraphDatabase

from app.core.config import settings
from app.services.graph_service import GraphService

# Intent keyword -> (relation type, target entity label) for the 1-hop traversals this
# retriever can do from JalurPendaftaran, matching what GraphService.index_document_entities
# actually writes (see graph_service.py's _JALUR_RELATIONS).
_INTENT_RELATIONS = {
    ("jadwal", "kapan", "waktu"): ("MEMILIKI_JADWAL", "Jadwal"),
    ("biaya", "bayar", "tarif"): ("MEMILIKI_BIAYA", "Biaya"),
    ("syarat", "persyaratan"): ("MENGHARUSKAN", "Persyaratan"),
}


def _detected_names(intent: str, entity_type: str) -> list[str]:
    """Names of `entity_type` GraphService.extract_entities recognizes in `intent`.

    `intent` (OrchestratorAgent's `graph_query`) is the resolved question plus expanded
    terms, not a bare category label -- so a question naming a specific jalur/program
    ("...jalur mandiri profesi...") already carries that name verbatim, extractable with
    the SAME keyword extractor graph ingestion uses (one definition of "what is an
    entity", per graph_service.py's own docstring)."""
    return [name for etype, name in GraphService.extract_entities(intent) if etype == entity_type]


class GraphRetrieverService:
    """Retrieve structured knowledge from Neo4j."""

    @staticmethod
    async def get_driver():
        """Get Neo4j driver."""
        return AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    @staticmethod
    async def retrieve_by_intent(intent: str) -> list[dict]:
        """Retrieve relevant entities/relationships by intent.

        Each result dict always has `entity_type`/`entity_name`. Results that came from a
        1-hop relation traversal (rather than a flat node scan) also carry `relation` and
        `related_to`, so callers (GraphReasoningAgent) can distinguish plain entity mentions
        from actual graph relationships.
        """
        driver = await GraphRetrieverService.get_driver()
        results = []
        intent_lower = intent.lower()

        try:
            async with driver.session() as session:
                # Program studi query
                if "program" in intent_lower or "jurusan" in intent_lower:
                    query = "MATCH (p:ProgramStudi) RETURN p.name as name LIMIT 5"
                    records = await session.run(query)
                    async for record in records:
                        results.append({
                            "entity_type": "ProgramStudi",
                            "entity_name": record["name"],
                            "relation": None,
                            "related_to": None,
                        })

                # Registration path query
                if "daftar" in intent_lower or "jalur" in intent_lower:
                    query = "MATCH (j:JalurPendaftaran) RETURN j.name as name LIMIT 5"
                    records = await session.run(query)
                    async for record in records:
                        results.append({
                            "entity_type": "JalurPendaftaran",
                            "entity_name": record["name"],
                            "relation": None,
                            "related_to": None,
                        })

                # Requirements query (flat, kept for backward compatibility)
                if "syarat" in intent_lower or "persyaratan" in intent_lower:
                    query = "MATCH (r:Persyaratan) RETURN r.name as name LIMIT 5"
                    records = await session.run(query)
                    async for record in records:
                        results.append({
                            "entity_type": "Persyaratan",
                            "entity_name": record["name"],
                            "relation": None,
                            "related_to": None,
                        })

                # Entity-aware scoping (2026-07-27): a question naming a specific jalur/program
                # ("...jalur mandiri profesi...") should get facts about THAT jalur, not a
                # generic top-10 sample across every jalur in the graph -- the un-scoped
                # version below returns identical results regardless of which jalur was asked
                # about, which measurably produced zero retrieval benefit for exactly this kind
                # of question (2026-07-26 GraphRAG isolation eval, segment 1: precision@5/
                # recall@5 delta=0.0 for the 6 questions designed to test this).
                jalur_names = _detected_names(intent, "JalurPendaftaran")
                program_names = _detected_names(intent, "ProgramStudi")

                # 1-hop relation traversals from JalurPendaftaran (jadwal/biaya/persyaratan),
                # so the answer can cite which jalur a given schedule/fee/requirement belongs to.
                for keywords, (relation, target_label) in _INTENT_RELATIONS.items():
                    if not any(kw in intent_lower for kw in keywords):
                        continue

                    if jalur_names:
                        query = (
                            f"MATCH (j:JalurPendaftaran)-[:{relation}]->(t:{target_label}) "
                            "WHERE j.name IN $jalur_names "
                            "RETURN j.name as jalur_name, t.name as target_name LIMIT 10"
                        )
                        records = await session.run(query, jalur_names=jalur_names)
                    else:
                        query = (
                            f"MATCH (j:JalurPendaftaran)-[:{relation}]->(t:{target_label}) "
                            "RETURN j.name as jalur_name, t.name as target_name LIMIT 10"
                        )
                        records = await session.run(query)
                    async for record in records:
                        results.append({
                            "entity_type": target_label,
                            "entity_name": record["target_name"],
                            "relation": relation,
                            "related_to": record["jalur_name"],
                        })

                    # 2-hop chain ProgramStudi-[:TERSEDIA_PADA]->JalurPendaftaran-[relation]->target,
                    # both legs of which GraphService.index_document_entities already writes (see
                    # graph_service.py's TERSEDIA_PADA merge) but which retrieve_by_intent never
                    # queried as a chain before this pass. Lets an answer attribute a schedule/fee/
                    # requirement to the specific program studi it applies to, not just the jalur.
                    # Scoped by jalur_names/program_names when the question named either, same
                    # rationale as the 1-hop query above. Full cross-document multi-hop reasoning
                    # stays out of scope (CLAUDE.md §11A.3/IMPLEMENTATION.md §5) — this only
                    # chains two relations that already exist for a single jalur, it does not
                    # traverse across documents.
                    chain_where = []
                    chain_params: dict = {}
                    if jalur_names:
                        chain_where.append("j.name IN $jalur_names")
                        chain_params["jalur_names"] = jalur_names
                    if program_names:
                        chain_where.append("p.name IN $program_names")
                        chain_params["program_names"] = program_names
                    chain_query = (
                        f"MATCH (p:ProgramStudi)-[:TERSEDIA_PADA]->(j:JalurPendaftaran)-[:{relation}]->(t:{target_label}) "
                        + (f"WHERE {' AND '.join(chain_where)} " if chain_where else "")
                        + "RETURN p.name as program_name, j.name as jalur_name, t.name as target_name LIMIT 10"
                    )
                    chain_records = await session.run(chain_query, **chain_params)
                    async for record in chain_records:
                        results.append({
                            "entity_type": target_label,
                            "entity_name": record["target_name"],
                            "relation": relation,
                            "related_to": record["jalur_name"],
                            "program_studi": record["program_name"],
                        })

        finally:
            await driver.close()

        return results
