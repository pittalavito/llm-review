"""Primary store for the RAG indices (keyspace rag-index).

Redis is the only store: no filesystem fallback, no in-memory fallback — a
missing or unreachable Redis is a startup error. The value is a typed
domain.store.redis.models.RagIndex (validated JSON).
"""
import re
from hashlib import sha256

from config import Config
from core.observability import LogPrefix, log_warning

from domain.store.redis.repository import RAG_INDEX_KEYSPACE
from domain.store.redis.repository import RedisRepository
from domain.store.redis.models import RagIndex


_UNSAFE_KEY_CHARS = re.compile(r"[^\w.\-/]")


class RedisRagIndexRepository(RedisRepository):
    """RAG index store backed by Redis. ttl_seconds <= 0 = permanent store."""

    def __init__(self, config: Config, ttl_seconds: int = 0):
        super().__init__(RAG_INDEX_KEYSPACE, config, ttl_seconds)

    @staticmethod
    def compute_doc_id(relative_path: str, strategy: str, strategy_version: str) -> str:
        """Human-readable index id, one per (paper, strategy, version):
        ``<slug>-<hash8>+<strategy>-<version>`` (e.g.
        ``papers/attention.pdf-3f9a1c2b+bm25-v1``).

        Because strategy and version are part of the id — hence of the Redis key —
        multiple strategies/versions of the same paper coexist instead of
        overwriting each other. The 8-char SHA-256 of the *original* path keeps the
        id collision-free even when two different paths slug to the same string."""
        slug = RedisRagIndexRepository._slug(relative_path)
        digest = sha256(relative_path.encode("utf-8")).hexdigest()[:8]
        paper_id = f"{slug}-{digest}"
        return f"{paper_id}+{RedisRagIndexRepository._slug(strategy)}-{RedisRagIndexRepository._slug(strategy_version)}"

    @staticmethod
    def _slug(text: str) -> str:
        return _UNSAFE_KEY_CHARS.sub("_", text)

    def load(self, doc_id: str) -> RagIndex | None:
        return self._load(doc_id, RagIndex, label="index")

    def save(self, index: RagIndex) -> None:
        self._set(index.doc_id, index.model_dump_json())

    def list_indexed(self) -> list[str]:
        """Unique paper_path for every index stored in Redis (SCAN + parse). A
        paper appears once even if indexed under several strategies/versions."""
        paper_paths: set[str] = set()
        for raw in self._scan_values():
            try:
                paper_paths.add(RagIndex.model_validate_json(raw).paper_path)
            except Exception:
                log_warning(LogPrefix.RAG_INDEX_REPOSITORY, "Skipping malformed index in Redis")
        return sorted(paper_paths)
