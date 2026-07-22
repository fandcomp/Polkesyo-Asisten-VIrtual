"""Query Neo4j for structured knowledge."""
from neo4j import AsyncGraphDatabase

from app.core.config import settings

# Intent keyword -> (relation type, target entity label) for the 1-hop traversals this
# retriever can do from JalurPendaftaran, matching what GraphService.index_document_entities
# actually writes (see graph_service.py's _JALUR_RELATIONS).
_INTENT_RELATIONS = {
    ("jadwal", "kapan", "waktu"): ("MEMILIKI_JADWAL", "Jadwal"),
    ("biaya", "bayar", "tarif"): ("MEMILIKI_BIAYA", "Biaya"),
    ("syarat", "persyaratan"): ("MENGHARUSKAN", "Persyaratan"),
}


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

                # 1-hop relation traversals from JalurPendaftaran (jadwal/biaya/persyaratan),
                # so the answer can cite which jalur a given schedule/fee/requirement belongs to.
                for keywords, (relation, target_label) in _INTENT_RELATIONS.items():
                    if not any(kw in intent_lower for kw in keywords):
                        continue
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

        finally:
            await driver.close()

        return results
