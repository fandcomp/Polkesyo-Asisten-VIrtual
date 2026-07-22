"""Deterministic ID generation for content that must survive re-ingestion unchanged.

`document_chunks.id` was previously assigned via `uuid4()` (random) at every ingestion run, so
re-ingesting the *same* document version produced entirely new chunk IDs. This silently broke
anything that pins a chunk ID across time — most notably `evaluation/gold_qa_dataset.jsonl`'s
`expected_chunk_ids`, which went stale the moment a document was ever re-indexed.

`chunk_id_for` derives a stable UUID from `(document_version_id, chunk_index)` via uuid5, so
re-ingesting an unchanged document version reproduces the same chunk IDs instead of new random
ones. This does NOT survive a document/version being deleted and recreated (a new
`document_version_id` is a different random UUID regardless) — only re-ingestion of an existing,
still-present version.
"""
from uuid import NAMESPACE_URL, UUID, uuid5

CHUNK_ID_NAMESPACE = uuid5(NAMESPACE_URL, "campus-va-chunk")


def chunk_id_for(document_version_id: UUID | str, chunk_index: int, chunk_kind: str = "text") -> UUID:
    """Deterministic chunk id from (document_version_id, chunk_index, chunk_kind).

    `chunk_kind` disambiguates text vs. visual chunks: both sequences are 0-based and
    independently indexed within the same document_version_id, so a text chunk and an image
    chunk can legitimately share the same chunk_index — without chunk_kind in the hash input
    they would collide on the same deterministic id.
    """
    return uuid5(CHUNK_ID_NAMESPACE, f"{document_version_id}:{chunk_kind}:{chunk_index}")
