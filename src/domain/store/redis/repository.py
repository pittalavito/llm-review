"""Redis persistence base for the Redis store, in one file: the ``RedisKeyspace``
registry (keyspace definitions), the ``Client`` (connect + ping, fail-fast) and
the ``RedisRepository`` base every concrete repository extends. Concrete
repositories live in their own files under domain/store/redis/.

Redis holds derived / cache data, kept separate from the SQL tables and the
domain models. Each keyspace is a flat namespace ``llm-review:<name>:<suffix>``,
so the Redis "schema" lives in one place.
"""
from dataclasses import dataclass
from typing import TypeVar

import redis
from pydantic import BaseModel

from config import Config
from core.observability import LogPrefix, observed, log_warning, log_info

_NAMESPACE = "llm-review"

_T = TypeVar("_T", bound=BaseModel)


@dataclass(frozen=True)
class RedisKeyspace:
    """One Redis keyspace: a key prefix plus a description of its value.

    ``name`` is the middle segment of the key; ``value`` documents the payload
    stored under it (the Python/JSON shape). ``persistent`` records whether keys
    are written without a TTL (permanent store) by default.
    """

    name: str
    value: str
    persistent: bool = True

    @property
    def prefix(self) -> str:
        """Key prefix, e.g. ``llm-review:rag-index:``."""
        return f"{_NAMESPACE}:{self.name}:"

    def key(self, suffix: str) -> str:
        """Full Redis key for a given id/suffix."""
        return f"{self.prefix}{suffix}"

    def pattern(self) -> str:
        """SCAN match pattern covering every key in this keyspace."""
        return f"{self.prefix}*"


RAG_INDEX_KEYSPACE = RedisKeyspace(
    name="rag-index",
    value=(
        "domain.store.redis.models.RagIndex as JSON — the RAG index for one paper. "
        "Suffix = SHA-256 of the paper's relative path. Derived data, rebuildable."
    ),
)

OPEN_REVIEW_CACHE_KEYSPACE = RedisKeyspace(
    name="open-review-cache",
    value=(
        "domain.store.redis.models.OpenReviewCache as JSON — the OpenReview notes cached for "
        "one paper. Suffix = paper filename stem. Re-fetched on a miss."
    ),
)

ALL_KEYSPACES: tuple[RedisKeyspace, ...] = (
    RAG_INDEX_KEYSPACE,
    OPEN_REVIEW_CACHE_KEYSPACE,
)


class Client:
    """Centralized Redis client creation. Redis is a hard dependency: an
    unreachable server is a startup error, never a silent degradation."""

    @staticmethod
    @observed(LogPrefix.REDIS_CLIENT)
    def create_redis_client(config: Config, purpose: str) -> "redis.Redis":
        """Connect to Redis and verify it responds. ``purpose`` names the store in
        logs and errors. Raises RuntimeError on failure — fail fast at boot."""
        try:
            client = redis.Redis.from_url(
                config.redis_url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=2,
            )
            client.ping()
        except redis.RedisError as exc:
            raise RuntimeError(f"Redis unreachable at {config.redis_url} — required for the {purpose}.") from exc
        log_info(LogPrefix.REDIS_CLIENT, "%s on Redis: %s", purpose, config.redis_url)
        return client


class RedisRepository:
    """Common plumbing: keyspace-prefixed keys and TTL-aware writes
    (ttl_seconds <= 0 = permanent store, the default)."""

    def __init__(self, keyspace: RedisKeyspace, config: Config, ttl_seconds: int = 0):
        self._client = Client.create_redis_client(config, f"{keyspace.name} store")
        self._keyspace = keyspace
        self._ttl = ttl_seconds

    def _get(self, suffix: str) -> str | None:
        """Raw value under this keyspace, or None if absent."""
        return self._client.get(self._keyspace.key(suffix))

    def _load(self, suffix: str, model_cls: type[_T], *, label: str) -> _T | None:
        """Read + validate one typed value: None if absent, and None with a
        warning if the stored JSON is malformed. The single (de)serialize path
        every concrete repository's ``load`` delegates to."""
        raw = self._get(suffix)
        if raw is None:
            return None
        try:
            return model_cls.model_validate_json(raw)
        except ValueError:
            log_warning(LogPrefix.REDIS_MALFORMED_DATA, "Discarding malformed %s in Redis: %s", label, suffix)
            return None

    def _set(self, suffix: str, value: str) -> None:
        """Write under this keyspace, applying the configured TTL."""
        key = self._keyspace.key(suffix)
        if self._ttl > 0:
            self._client.set(key, value, ex=self._ttl)
        else:
            self._client.set(key, value)

    def _scan_values(self):
        """Yield every raw value stored in this keyspace (SCAN, no blocking KEYS)."""
        for key in self._client.scan_iter(match=self._keyspace.pattern()):
            raw = self._client.get(key)
            if raw is not None:
                yield raw

    def dump_items(self) -> dict[str, str]:
        """Every (suffix, raw value) in this keyspace — the backup export."""
        items: dict[str, str] = {}
        prefix_length = len(self._keyspace.prefix)
        for key in self._client.scan_iter(match=self._keyspace.pattern()):
            raw = self._client.get(key)
            if raw is not None:
                items[key[prefix_length:]] = raw
        return items

    def restore_item(self, suffix: str, raw: str) -> bool:
        """Insert one raw value if the key is absent (existing data wins). True
        when written."""
        return bool(self._client.setnx(self._keyspace.key(suffix), raw))

    def _delete(self, suffix: str) -> None:
        """Remove one key from this keyspace (absent key = no-op)."""
        self._client.delete(self._keyspace.key(suffix))

    def _delete_prefix(self, suffix_prefix: str) -> int:
        """Remove every key whose suffix starts with the given prefix. Returns the
        number of keys removed."""
        keys = list(self._client.scan_iter(match=self._keyspace.key(suffix_prefix) + "*"))
        if keys:
            self._client.delete(*keys)
        return len(keys)
