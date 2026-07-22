"""Neo4j Knowledge Graph management."""
import re

from neo4j import AsyncGraphDatabase
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

# Entity types this extractor actually produces — used to whitelist Cypher label
# interpolation (labels can't be parameterized in Cypher, so we validate against
# a fixed set instead of trusting arbitrary strings).
ALLOWED_ENTITY_TYPES = {
    "ProgramStudi",
    "JalurPendaftaran",
    "TahapSeleksi",
    "Persyaratan",
    "Jadwal",
    "Biaya",
}

# Real program names found across actual SPMB documents (Pedoman/Brosur SPMB) —
# supersedes the earlier 4-program placeholder list, which missed most programs.
_PROGRAM_STUDI = [
    "D-III Teknologi Laboratorium Medis",
    "Sarjana Terapan Teknologi Laboratorium Medis",
    "D-III Gizi",
    "Sarjana Terapan Gizi dan Dietetika",
    "D-III Kebidanan",
    "Sarjana Terapan Kebidanan",
    "D-III Rekam Medis dan Informasi Kesehatan",
    "D-III Keperawatan",
    "Sarjana Terapan Keperawatan",
    "Sarjana Terapan Keperawatan Anestesiologi",
    "D-III Kesehatan Gigi",
    "Sarjana Terapan Terapi Gigi",
    "D-III Sanitasi",
    "Sarjana Terapan Sanitasi Lingkungan",
]

# Real jalur names found in actual documents. "SNMPTN" never appears in any real
# Poltekkes Kemenkes Yogyakarta document and has been dropped — it was a wrong
# placeholder value left over from a generic template.
_JALUR_PENDAFTARAN = [
    "SPMB Mandiri Reguler SMA",
    "SPMB Mandiri Profesi",
    "SPMB Mandiri RPL",
    "SPMB Mandiri STR RPL",
    "SPMB Bersama",
    "SPMB Prestasi",
    "SPMB Profesi",
    "Jalur Mandiri",
]

_KEYWORD_ENTITIES = {
    "Persyaratan": [
        "KTP",
        "NPWP",
        "ijazah",
        "surat",
        "sehat jasmani",
        "buta warna",
        "tinggi badan",
    ],
    "TahapSeleksi": ["ujian tulis", "ujian kesehatan", "wawancara", "CBT", "verifikasi berkas"],
}

_MONTHS = (
    "Januari|Februari|Maret|April|Mei|Juni|Juli|Agustus|September|Oktober|November|Desember"
)
# Matches a date or date-range like "28 April 2026 s/d 10 Juni 2026" or "10 Juni 2026". Written
# to match equally well inside a raw Jadwal table row (extracted PDF text, cells on separate
# lines) and inside an LLM-paraphrased chunk summary sentence (e.g. "Pendaftaran dibuka pada 28
# April 2026 sampai dengan 10 Juni 2026") — extraction runs on chunk *summaries*, not raw text.
# Alternatives are ordered longest-first so a full two-sided range collapses into one match
# instead of two overlapping ones.
_CONNECTOR = r"(?:s/d|s\.d\.|sampai(?:\s+dengan)?)"
_DATE_RE = re.compile(
    rf"\d{{1,2}}\s+(?:{_MONTHS})\s+20\d{{2}}\s*{_CONNECTOR}\s*\d{{1,2}}\s+(?:{_MONTHS})\s+20\d{{2}}"
    rf"|\d{{1,2}}\s*{_CONNECTOR}\s*\d{{1,2}}\s+(?:{_MONTHS})\s+20\d{{2}}"
    rf"|\d{{1,2}}\s+(?:{_MONTHS})\s+20\d{{2}}",
    re.IGNORECASE,
)
# Matches "<label text> sebesar Rp 300.000" / "Rp. 100.000,-" style fee mentions.
_BIAYA_RE = re.compile(
    r"([^.\n]{0,40}?)\s*(?:sebesar\s+)?Rp\.?\s?(\d[\d.,]*)",
    re.IGNORECASE,
)

# Relation types written from JalurPendaftaran to other entity types found in the same
# document — CLAUDE.md §14's relation vocabulary, grounded in what real documents contain
# (a Pedoman/Brosur SPMB names one jalur in its title and lists that jalur's own jadwal,
# biaya, and persyaratan in its body).
_JALUR_RELATIONS = {
    "Jadwal": "MEMILIKI_JADWAL",
    "Biaya": "MEMILIKI_BIAYA",
    "Persyaratan": "MENGHARUSKAN",
}


class GraphService:
    """Manage Neo4j knowledge graph."""

    @staticmethod
    async def get_driver():
        """Get Neo4j driver."""
        return AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )

    @staticmethod
    async def index_document_by_id(db: AsyncSession, document_id: str) -> dict | None:
        """Look up a document's title and approved chunk summaries, then index it.

        Shared by the manual `POST /admin/graph/index-document` endpoint and the
        auto-index-on-approve path so both call one implementation instead of
        duplicating the doc/summary lookup.
        """
        from app.db.models import ChunkSummary, Document, DocumentChunk

        stmt = select(Document).where(Document.id == document_id)
        doc_result = await db.execute(stmt)
        doc = doc_result.scalars().first()
        if not doc:
            return None

        # Keep chunk_id alongside each summary (instead of the old flat list of summary
        # strings) so admin-curated chunk_entities rows can be resolved per chunk below —
        # both lists are built from the same filtered rows, so they stay index-aligned.
        stmt = (
            select(DocumentChunk.id, ChunkSummary.approved_summary)
            .join(ChunkSummary, ChunkSummary.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.document_id == document_id)
        )
        rows_result = await db.execute(stmt)
        rows = [(chunk_id, summary) for chunk_id, summary in rows_result.all() if summary]
        chunk_ids = [r[0] for r in rows]
        summaries = [r[1] for r in rows]

        overrides = await GraphService._resolve_chunk_entity_overrides(db, chunk_ids)

        return await GraphService.index_document_entities(
            str(document_id), doc.title, summaries, overrides
        )

    @staticmethod
    async def _resolve_chunk_entity_overrides(
        db: AsyncSession, chunk_ids: list
    ) -> list[list[tuple[str, str]] | None]:
        """Per-chunk entity-list resolution for reindexing (index-aligned with `chunk_ids`).

        For each chunk: `None` means it has zero `chunk_entities` rows at all — the caller
        must fall back to live `extract_entities(summary)` for that chunk (backward
        compatibility for documents ingested before this feature existed, or not yet opened
        in the admin entity panel). A list (possibly empty) means the chunk HAS rows — only
        `confirmed`/`edited` ones contribute, using `corrected_text or detected_text` /
        `corrected_type or entity_type`; `detected` (never reviewed) and `rejected` rows are
        excluded. An admin correction never renames an existing shared Neo4j node in place —
        it only changes which (type, name) pair this chunk resolves to, which the MERGE below
        creates-if-missing or reuses exactly as before.
        """
        from app.db.models import ChunkEntity

        if not chunk_ids:
            return []

        stmt = select(ChunkEntity).where(ChunkEntity.chunk_id.in_(chunk_ids))
        result = await db.execute(stmt)
        by_chunk: dict[str, list] = {}
        for row in result.scalars().all():
            by_chunk.setdefault(str(row.chunk_id), []).append(row)

        overrides: list[list[tuple[str, str]] | None] = []
        for chunk_id in chunk_ids:
            chunk_rows = by_chunk.get(str(chunk_id))
            if chunk_rows is None:
                overrides.append(None)
                continue
            curated = [
                (row.corrected_type or row.entity_type, row.corrected_text or row.detected_text)
                for row in chunk_rows
                if row.status in ("confirmed", "edited")
            ]
            overrides.append(curated)
        return overrides

    @staticmethod
    async def index_document_entities(
        doc_id: str,
        doc_title: str,
        chunk_summaries: list[str],
        chunk_entity_overrides: list[list[tuple[str, str]] | None] | None = None,
    ) -> dict:
        """Index document entities and relationships.

        Extracts entities from every chunk summary, links each back to the document for
        citation provenance (`Document-[:MENTIONS]->Entity`), and — since a Pedoman/Brosur
        SPMB document is always about one jalur pendaftaran, usually named in its own
        title — links that document's primary jalur to whichever Jadwal/Biaya/Persyaratan/
        ProgramStudi entities were found anywhere in it.

        `chunk_entity_overrides`, when given, is index-aligned with `chunk_summaries`: `None`
        at a given index means that chunk has no `chunk_entities` rows yet, so this falls back
        to the original behavior of live `extract_entities(summary)` for that chunk only; a
        list (possibly empty) means the chunk has admin-curated entities (confirmed/edited
        only — see `_resolve_chunk_entity_overrides`) and that list is used verbatim instead.
        """
        driver = await GraphService.get_driver()
        result = {"created_nodes": 0, "created_relationships": 0, "errors": []}

        primary_jalur = GraphService._detect_primary_jalur(doc_title, chunk_summaries)

        try:
            async with driver.session() as session:
                await session.run(
                    """
                    MERGE (d:Document {id: $id})
                    ON CREATE SET d.title = $title, d.status = 'active', d.created_at = datetime()
                    ON MATCH SET d.title = $title, d.updated_at = datetime()
                    """,
                    id=doc_id,
                    title=doc_title,
                )
                result["created_nodes"] += 1

                doc_program_studi: set[str] = set()
                doc_related_entities: set[tuple[str, str]] = set()

                for chunk_index, summary in enumerate(chunk_summaries):
                    override = (
                        chunk_entity_overrides[chunk_index] if chunk_entity_overrides else None
                    )
                    # override is None => no chunk_entities rows for this chunk yet (legacy /
                    # backward-compat path); a list (possibly empty) => admin-curated entities.
                    entities = (
                        GraphService.extract_entities(summary) if override is None else override
                    )
                    for entity_type, entity_name in entities:
                        if entity_type not in ALLOWED_ENTITY_TYPES:
                            continue
                        try:
                            # Safety property: this MERGE only ever creates-if-missing or
                            # reuses the existing shared node matched by (label, name). An
                            # admin correction (corrected_text/corrected_type) changes which
                            # (type, name) pair this chunk resolves to on the NEXT reindex —
                            # it never issues a SET/rename against a node matched by the old
                            # name, so a node other documents still reference via their own
                            # MENTIONS edge is never mutated in place.
                            await session.run(
                                f"""
                                MERGE (e:{entity_type} {{name: $name}})
                                ON CREATE SET e.source_document_id = $doc_id,
                                              e.status = 'indexed',
                                              e.created_at = datetime()
                                ON MATCH SET e.updated_at = datetime()
                                WITH e
                                MATCH (d:Document {{id: $doc_id}})
                                MERGE (d)-[:MENTIONS]->(e)
                                """,
                                name=entity_name,
                                doc_id=doc_id,
                            )
                            result["created_nodes"] += 1

                            if entity_type == "ProgramStudi":
                                doc_program_studi.add(entity_name)
                            elif entity_type in _JALUR_RELATIONS:
                                doc_related_entities.add((entity_type, entity_name))
                        except Exception as e:
                            result["errors"].append(str(e))

                if primary_jalur:
                    for entity_type, entity_name in doc_related_entities:
                        relation = _JALUR_RELATIONS[entity_type]
                        try:
                            await session.run(
                                f"""
                                MATCH (j:JalurPendaftaran {{name: $jalur_name}})
                                MATCH (target:{entity_type} {{name: $target_name}})
                                MERGE (j)-[:{relation}]->(target)
                                """,
                                jalur_name=primary_jalur,
                                target_name=entity_name,
                            )
                            result["created_relationships"] += 1
                        except Exception as e:
                            result["errors"].append(str(e))

                    for program_name in doc_program_studi:
                        try:
                            await session.run(
                                """
                                MATCH (p:ProgramStudi {name: $prog_name})
                                MATCH (j:JalurPendaftaran {name: $jalur_name})
                                MERGE (p)-[:TERSEDIA_PADA]->(j)
                                """,
                                prog_name=program_name,
                                jalur_name=primary_jalur,
                            )
                            result["created_relationships"] += 1
                        except Exception as e:
                            result["errors"].append(str(e))

        except Exception as e:
            result["error"] = str(e)

        finally:
            await driver.close()

        return result

    @staticmethod
    def _detect_primary_jalur(doc_title: str, chunk_summaries: list[str]) -> str | None:
        """Pick the one JalurPendaftaran this document is primarily about.

        Prefers the document title (Pedoman/Brosur SPMB titles reliably name their jalur),
        falling back to the most-mentioned jalur across chunk summaries.
        """
        for jalur in _JALUR_PENDAFTARAN:
            if jalur.lower() in doc_title.lower():
                return jalur

        counts: dict[str, int] = {}
        combined = " ".join(chunk_summaries).lower()
        for jalur in _JALUR_PENDAFTARAN:
            count = combined.count(jalur.lower())
            if count:
                counts[jalur] = count
        if not counts:
            return None
        return max(counts, key=counts.get)

    @staticmethod
    def extract_entities(text: str) -> list[tuple[str, str]]:
        """Keyword/pattern-based entity extraction.

        Shared utility — also used by DocumentManagementService to surface
        detected entities in the chunk review UI, so both the graph ingestion
        path and the admin review path stay in sync on what counts as an
        entity instead of maintaining two keyword lists.
        """
        entities: list[tuple[str, str]] = []
        lower_text = text.lower()

        for prog in _PROGRAM_STUDI:
            if prog.lower() in lower_text:
                entities.append(("ProgramStudi", prog))

        for jalur in _JALUR_PENDAFTARAN:
            if jalur.lower() in lower_text:
                entities.append(("JalurPendaftaran", jalur))

        for entity_type, keywords_list in _KEYWORD_ENTITIES.items():
            for kw in keywords_list:
                if kw.lower() in lower_text:
                    entities.append((entity_type, kw))

        entities.extend(GraphService._extract_jadwal(text))
        entities.extend(GraphService._extract_biaya(text))

        return entities

    @staticmethod
    def _extract_jadwal(text: str) -> list[tuple[str, str]]:
        """Pull activity/date-range mentions out of the text.

        Works both on raw Jadwal table extractions (activity and date on separate lines) and
        on LLM-paraphrased chunk summaries (a single prose sentence) — for each date match, the
        nearest preceding sentence/line fragment (up to the last '.', ',' or newline) is treated
        as the activity label, e.g. "Pendaftaran: 28 April 2026 s/d 10 Juni 2026".
        """
        entities: list[tuple[str, str]] = []

        for match in _DATE_RE.finditer(text):
            preceding = text[max(0, match.start() - 60) : match.start()]
            label = re.split(r"[.\n]", preceding)[-1].strip(" ,:-")
            if label and any(c.isalpha() for c in label):
                entities.append(("Jadwal", f"{label}: {match.group(0)}"))

        return entities

    @staticmethod
    def _extract_biaya(text: str) -> list[tuple[str, str]]:
        """Pull fee mentions like 'Biaya pendaftaran sebesar Rp 300.000' out of the text."""
        entities: list[tuple[str, str]] = []
        for match in _BIAYA_RE.finditer(text):
            label = match.group(1).strip(" .,-")
            amount = match.group(2).strip()
            if label and any(c.isalpha() for c in label):
                entities.append(("Biaya", f"{label} Rp {amount}"))
        return entities

    @staticmethod
    async def query_entities(entity_type: str) -> list[dict]:
        """Query entities from graph."""
        if entity_type not in ALLOWED_ENTITY_TYPES:
            return []

        driver = await GraphService.get_driver()

        try:
            async with driver.session() as session:
                result = await session.run(
                    f"MATCH (e:{entity_type}) RETURN e.name as name LIMIT 10"
                )
                entities = [record["name"] async for record in result]
                return [{"name": e, "type": entity_type} for e in entities]

        finally:
            await driver.close()

    @staticmethod
    def _entity_node_id(entity_type: str, name: str) -> str:
        """Stable node id for the graph-viewer JSON contract — entity nodes only have a
        `name` property (unique within a label, not globally), so prefix with the label to
        avoid an accidental id collision between two different entity types sharing a name.
        """
        return f"{entity_type}:{name}"

    @staticmethod
    async def get_graph_for_document(document_id: str) -> dict:
        """Read-only: nodes + edges for one document's approved knowledge-graph evidence,
        shaped for the admin Knowledge Graph panel (CLAUDE.md §11A.4 — Neo4j is the only
        store for this, queried directly, never mirrored into Postgres).

        Returns `{"nodes": [...], "edges": [...]}` — nodes include the Document itself plus
        every entity it `MENTIONS`; edges include that MENTIONS relation plus any relation
        Neo4j already has between two entities both mentioned by this same document (e.g.
        JalurPendaftaran -[:MEMILIKI_BIAYA]-> Biaya), so the "how KG reasoning works" story
        is visible, not just a flat entity list.
        """
        driver = await GraphService.get_driver()
        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        try:
            async with driver.session() as session:
                doc_result = await session.run(
                    "MATCH (d:Document {id: $doc_id}) RETURN d.title as title",
                    doc_id=document_id,
                )
                doc_record = await doc_result.single()
                if doc_record is None:
                    return {"nodes": [], "edges": []}

                nodes[document_id] = {
                    "id": document_id,
                    "label": doc_record["title"] or document_id,
                    "type": "Document",
                }

                mentions_result = await session.run(
                    """
                    MATCH (d:Document {id: $doc_id})-[:MENTIONS]->(e)
                    RETURN labels(e) as labels, e.name as name
                    """,
                    doc_id=document_id,
                )
                async for record in mentions_result:
                    entity_labels = [l for l in record["labels"] if l in ALLOWED_ENTITY_TYPES]
                    if not entity_labels:
                        continue
                    entity_type = entity_labels[0]
                    node_id = GraphService._entity_node_id(entity_type, record["name"])
                    nodes[node_id] = {"id": node_id, "label": record["name"], "type": entity_type}
                    edges.append({"source": document_id, "target": node_id, "type": "MENTIONS"})

                relations_result = await session.run(
                    """
                    MATCH (d:Document {id: $doc_id})-[:MENTIONS]->(e1)
                    MATCH (d)-[:MENTIONS]->(e2)
                    MATCH (e1)-[r]->(e2)
                    WHERE type(r) <> 'MENTIONS'
                    RETURN labels(e1) as e1_labels, e1.name as e1_name,
                           type(r) as rel_type,
                           labels(e2) as e2_labels, e2.name as e2_name
                    """,
                    doc_id=document_id,
                )
                async for record in relations_result:
                    e1_labels = [l for l in record["e1_labels"] if l in ALLOWED_ENTITY_TYPES]
                    e2_labels = [l for l in record["e2_labels"] if l in ALLOWED_ENTITY_TYPES]
                    if not e1_labels or not e2_labels:
                        continue
                    source_id = GraphService._entity_node_id(e1_labels[0], record["e1_name"])
                    target_id = GraphService._entity_node_id(e2_labels[0], record["e2_name"])
                    edges.append({"source": source_id, "target": target_id, "type": record["rel_type"]})

        finally:
            await driver.close()

        return {"nodes": list(nodes.values()), "edges": edges}

    @staticmethod
    async def get_graph_global(limit: int = 150) -> dict:
        """Read-only: a capped global snapshot of the knowledge graph (all entity types +
        their relations), for the admin panel's "all documents" view. Capped since the full
        graph (hundreds of nodes) would overwhelm a force-directed layout in the browser.
        """
        driver = await GraphService.get_driver()
        nodes: dict[str, dict] = {}
        edges: list[dict] = []

        try:
            async with driver.session() as session:
                nodes_result = await session.run(
                    """
                    MATCH (e)
                    WHERE any(l IN labels(e) WHERE l IN $allowed_types)
                    RETURN labels(e) as labels, e.name as name
                    LIMIT $limit
                    """,
                    allowed_types=list(ALLOWED_ENTITY_TYPES),
                    limit=limit,
                )
                async for record in nodes_result:
                    entity_labels = [l for l in record["labels"] if l in ALLOWED_ENTITY_TYPES]
                    if not entity_labels:
                        continue
                    entity_type = entity_labels[0]
                    node_id = GraphService._entity_node_id(entity_type, record["name"])
                    nodes[node_id] = {"id": node_id, "label": record["name"], "type": entity_type}

                if nodes:
                    edges_result = await session.run(
                        """
                        MATCH (e1)-[r]->(e2)
                        WHERE any(l IN labels(e1) WHERE l IN $allowed_types)
                          AND any(l IN labels(e2) WHERE l IN $allowed_types)
                          AND type(r) <> 'MENTIONS'
                        RETURN labels(e1) as e1_labels, e1.name as e1_name,
                               type(r) as rel_type,
                               labels(e2) as e2_labels, e2.name as e2_name
                        LIMIT $limit
                        """,
                        allowed_types=list(ALLOWED_ENTITY_TYPES),
                        limit=limit,
                    )
                    async for record in edges_result:
                        e1_labels = [l for l in record["e1_labels"] if l in ALLOWED_ENTITY_TYPES]
                        e2_labels = [l for l in record["e2_labels"] if l in ALLOWED_ENTITY_TYPES]
                        if not e1_labels or not e2_labels:
                            continue
                        source_id = GraphService._entity_node_id(e1_labels[0], record["e1_name"])
                        target_id = GraphService._entity_node_id(e2_labels[0], record["e2_name"])
                        if source_id not in nodes or target_id not in nodes:
                            continue
                        edges.append({"source": source_id, "target": target_id, "type": record["rel_type"]})

        finally:
            await driver.close()

        return {"nodes": list(nodes.values()), "edges": edges}
