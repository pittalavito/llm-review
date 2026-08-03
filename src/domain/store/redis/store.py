"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the Redis translation seams as
static-method classes. ``Adapter`` (reads) parses the stored records into domain
models: ``RagIndex`` -> ``IndexInfo`` + full paper text. ``Factory`` (writes)
has nothing to build yet — the Redis records are stored as-is — but exists for
symmetry with the DB store.
"""
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from models.store.redis import RagIndex as StoreRagIndex

from models.domain.retrieval import IndexInfo, RagIndex

__all__ = ["RedisRagIndexRepository", "Adapter", "Factory"]


class Adapter:
    """Read seam: Redis records -> domain models (RAG index)."""

    @staticmethod
    def to_rag_index(record: StoreRagIndex) -> RagIndex:
        """Store ``RagIndex`` record -> domain ``RagIndex`` (deserialization only —
        same shape)."""
        return RagIndex.model_validate(record.model_dump())

    @staticmethod
    def to_index_info(index: RagIndex) -> IndexInfo:
        """``RagIndex`` record -> lightweight ``IndexInfo`` (metadata only)."""
        return IndexInfo(doc_id=index.doc_id, paper_id=index.paper_id, section_count=len(index.sections))

    @staticmethod
    def to_full_paper_text(index: RagIndex) -> str:
        """Reassemble the whole paper from the index sections, in order, each with
        its heading — the full-context text handed to every agent."""
        return "\n\n".join(f"# {section.name}\n{section.text}" for section in index.sections)


class Factory:
    """Write seam: domain models -> Redis records (deserialization only — same
    shape)."""

    @staticmethod
    def to_rag_index_record(index: RagIndex) -> StoreRagIndex:
        """Domain ``RagIndex`` -> store ``RagIndex`` record."""
        return StoreRagIndex.model_validate(index.model_dump())
