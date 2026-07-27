"""Cache store for OpenReview responses (keyspace open-review-cache).

Redis is the only store: an unreachable Redis is a startup error, not a silent
degradation. The value is a typed domain.store.redis.models.OpenReviewCache (validated JSON).
"""
from domain.store.redis.repository import OPEN_REVIEW_CACHE_KEYSPACE
from domain.store.redis.repository import RedisRepository
from domain.store.redis.models import OpenReviewCache


class RedisOpenReviewCacheRepository(RedisRepository):
    """OpenReview response cache backed by Redis. ttl_seconds <= 0 = permanent."""

    def __init__(self, ttl_seconds: int = 0):
        super().__init__(OPEN_REVIEW_CACHE_KEYSPACE, ttl_seconds)
    
    def load(self, key: str) -> OpenReviewCache | None:
        return self._load(key, OpenReviewCache, label="OpenReview cache")

    def save(self, key: str, cache: OpenReviewCache) -> None:
        self._set(key, cache.model_dump_json())
