"""Primary store for the RAG indices (keyspace rag-index).

Redis is the only store: no filesystem fallback, no in-memory fallback — a
missing or unreachable Redis is a startup error. The value is a typed
models.store.redis.RagIndex (validated JSON).
"""
import re

from core.observability import LogPrefix, log_warning

from domain.store.redis.repository import RAG_INDEX_KEYSPACE
from domain.store.redis.repository import RedisRepository
from models.store.redis import RagIndex


_UNSAFE_KEY_CHARS = re.compile(r"[^\w.\-/]")


class RedisRagIndexRepository(RedisRepository):
    """RAG index store backed by Redis. ttl_seconds <= 0 = permanent store."""

    def __init__(self, ttl_seconds: int = 0):
        super().__init__(RAG_INDEX_KEYSPACE, ttl_seconds)

    @staticmethod
    def compute_doc_id(paper_id: str, strategy: str, strategy_version: str) -> str:
        """Human-readable index id, one per (paper, strategy, version):
        ``<paper_id>+<strategy>-<version>`` (e.g.
        ``other_attention_pdf+bm25-v1``).

        Because strategy and version are part of the id — hence of the Redis key —
        multiple strategies/versions of the same paper coexist instead of
        overwriting each other. ``paper_id`` is already unique and Redis-safe, so
        no slug/hash of the old file path is needed."""
        return f"{paper_id}+{RedisRagIndexRepository._slug(strategy)}-{RedisRagIndexRepository._slug(strategy_version)}"

    @staticmethod
    def _slug(text: str) -> str:
        return _UNSAFE_KEY_CHARS.sub("_", text)

    def load(self, doc_id: str) -> RagIndex | None:
        return self._load(doc_id, RagIndex, label="index")

    def save(self, index: RagIndex) -> None:
        self._set(index.doc_id, index.model_dump_json())

    def list_indexed(self) -> list[str]:
        """Unique paper_id for every index stored in Redis (SCAN + parse). A
        paper appears once even if indexed under several strategies/versions."""
        paper_ids: set[str] = set()
        for raw in self._scan_values():
            try:
                paper_ids.add(RagIndex.model_validate_json(raw).paper_id)
            except Exception:
                log_warning(LogPrefix.RAG_INDEX_REPOSITORY, "Skipping malformed index in Redis")
        return sorted(paper_ids)
