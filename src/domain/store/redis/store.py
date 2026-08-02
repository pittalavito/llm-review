"""Redis store facade: one import point for the Redis persistence layer.

Re-exports the Redis repositories and holds the Redis translation seams as
static-method classes. ``Adapter`` (reads) parses the stored records into domain
models: ``RagIndex`` -> ``IndexInfo`` + full paper text, and ``OpenReviewCache``
-> ``HumanReview`` / ``HumanMetaReview`` / decision (handling OpenReview v1 and
v2). ``Factory`` (writes) has nothing to build yet — the Redis records are stored
as-is — but exists for symmetry with the DB store.
"""
import re

from domain.store.redis.open_review_repository import RedisOpenReviewCacheRepository
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from models.store.redis import OpenReviewCache as StoreOpenReviewCache, RagIndex as StoreRagIndex

from models.domain.comparator import HumanMetaReview, HumanReview
from models.domain.openreview import OpenReviewCache
from models.domain.retrieval import IndexInfo, RagIndex

__all__ = ["RedisRagIndexRepository", "RedisOpenReviewCacheRepository", "Adapter", "Factory"]


_REVIEW_KW = {"official_review", "official review"}
_META_KW = {"meta_review", "meta review", "metareview"}
_DECISION_KW = {"decision"}


class Adapter:
    """Read seam: Redis records -> domain models (with OpenReview note parsing)."""

    @staticmethod
    def to_rag_index(record: StoreRagIndex) -> RagIndex:
        """Store ``RagIndex`` record -> domain ``RagIndex`` (deserialization only —
        same shape)."""
        return RagIndex.model_validate(record.model_dump())

    @staticmethod
    def to_open_review_cache(record: StoreOpenReviewCache) -> OpenReviewCache:
        """Store ``OpenReviewCache`` record -> domain ``OpenReviewCache``
        (deserialization only — same shape)."""
        return OpenReviewCache.model_validate(record.model_dump())

    @staticmethod
    def to_index_info(index: RagIndex) -> IndexInfo:
        """``RagIndex`` record -> lightweight ``IndexInfo`` (metadata only)."""
        return IndexInfo(doc_id=index.doc_id, paper_id=index.paper_id, section_count=len(index.sections))

    @staticmethod
    def to_full_paper_text(index: RagIndex) -> str:
        """Reassemble the whole paper from the index sections, in order, each with
        its heading — the full-context text handed to every agent."""
        return "\n\n".join(f"# {section.name}\n{section.text}" for section in index.sections)

    @staticmethod
    def to_human_reviews(cache: OpenReviewCache) -> list[HumanReview]:
        """Parse the cached OpenReview notes into structured human reviews."""
        reviews: list[HumanReview] = []
        for note in cache.to_notes():
            if not any(kw in Adapter.invitation_text(note) for kw in _REVIEW_KW):
                continue
            content = Adapter.unwrap(note.get("content", {}))
            rating_raw = Adapter.get(content, "rating", "recommendation")
            conf_raw = Adapter.get(content, "confidence")
            # NeurIPS (and ICLR 2024+) sub-scores, e.g. "3 good" — None elsewhere.
            soundness_raw = Adapter.get(content, "soundness")
            presentation_raw = Adapter.get(content, "presentation")
            contribution_raw = Adapter.get(content, "contribution")
            reviews.append(HumanReview(
                note_id=note.get("id", ""),
                reviewer_id=str((note.get("signatures") or ["?"])[0]).split("/")[-1],
                summary=Adapter.get(content, "summary_of_the_paper", "summary"),
                strengths=Adapter.get(content, "strengths", "strength_and_weaknesses", "strengths_and_weaknesses"),
                weaknesses=Adapter.get(content, "weaknesses"),
                full_text=Adapter.get(content, "review", "main_review"),
                rating=Adapter.extract_int(rating_raw),
                rating_label=rating_raw,
                confidence=Adapter.extract_int(conf_raw),
                confidence_label=conf_raw,
                questions=Adapter.get(content, "questions", "summary_of_the_review"),
                limitations=Adapter.get(content, "limitations"),
                soundness=Adapter.extract_int(soundness_raw),
                soundness_label=soundness_raw,
                presentation=Adapter.extract_int(presentation_raw),
                presentation_label=presentation_raw,
                contribution=Adapter.extract_int(contribution_raw),
                contribution_label=contribution_raw,
            ))
        return reviews

    
    @staticmethod
    def extract_int(value: object) -> int | None:
        """Leading integer from strings like '6: marginally above...'."""
        if value is None:
            return None
        m = re.match(r"(\d+)", str(value).strip())
        return int(m.group(1)) if m else None
    
    @staticmethod
    def to_human_meta_review(cache: OpenReviewCache) -> HumanMetaReview | None:
        """Parse the cached notes into the human meta-review, if present."""
        for note in cache.to_notes():
            if not any(kw in Adapter.invitation_text(note) for kw in _META_KW):
                continue
            content = Adapter.unwrap(note.get("content", {}))
            return HumanMetaReview(
                note_id=note.get("id", ""),
                text=Adapter.get(content, "metareview", "meta_review", "comment", "summary"),
                recommendation=Adapter.get(content, "recommendation", "decision"),
            )
        return None

    @staticmethod
    def to_open_review_decision(cache: OpenReviewCache) -> str | None:
        """Parse the cached notes into the human decision, if present."""
        for note in cache.to_notes():
            if not any(kw in Adapter.invitation_text(note) for kw in _DECISION_KW):
                continue
            decision = Adapter.get(Adapter.unwrap(note.get("content", {})), "decision", "recommendation")
            if decision:
                return decision
        return None
    
    @staticmethod
    def unwrap(content: dict) -> dict:
        """OpenReview v2 wraps each field as ``{"value": ...}``; flatten to the value."""
        return {k: (v["value"] if isinstance(v, dict) and "value" in v else v) for k, v in content.items()}

    @staticmethod
    def invitation_text(note: dict) -> str:
        """Lowercased invitation string, handling v1 (``invitation`` str) and v2
        (``invitations`` list)."""
        raw = note.get("invitation") or note.get("invitations") or ""
        if isinstance(raw, (list, tuple)):
            raw = " ".join(str(x) for x in raw)
        return str(raw).lower()

    @staticmethod
    def get(content: dict, *keys: str) -> str | None:
        for key in keys:
            value = content.get(key)
            if value:
                return value if isinstance(value, str) else str(value)
        return None
    
class Factory:
    """Write seam: domain models -> Redis records (deserialization only — same
    shape)."""

    @staticmethod
    def to_rag_index_record(index: RagIndex) -> StoreRagIndex:
        """Domain ``RagIndex`` -> store ``RagIndex`` record."""
        return StoreRagIndex.model_validate(index.model_dump())

    @staticmethod
    def to_open_review_cache_record(cache: OpenReviewCache) -> StoreOpenReviewCache:
        """Domain ``OpenReviewCache`` -> store ``OpenReviewCache`` record."""
        return StoreOpenReviewCache.model_validate(cache.model_dump())
