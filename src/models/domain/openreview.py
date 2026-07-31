"""Domain models for the OpenReview cache: a domain replica of the stored
``models.store.redis.OpenReviewCache`` record (same shape, converted by
deserialization). The structured ``HumanReview`` / ``HumanMetaReview`` parsed out
of it live in ``domain/models/comparator.py``."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpenReviewCacheNote(BaseModel):
    """A single OpenReview note (one entry of a forum thread). Only the fields the
    pipeline reads are typed; everything else round-trips via extra="allow"."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    number: int | None = None
    forum: str | None = None
    replyto: str | None = None
    invitation: str | None = None
    """v1 API: single invitation string."""
    invitations: list[str] | None = None
    """v2 API: list of invitations."""
    signatures: list[str] = Field(default_factory=list)
    content: dict[str, Any] = Field(default_factory=dict)


class OpenReviewCache(BaseModel):
    """Cache of one paper's OpenReview response: the list of its notes."""

    notes: list[OpenReviewCacheNote] = Field(default_factory=list)

    @classmethod
    def from_notes(cls, notes: list[dict]) -> "OpenReviewCache":
        return cls(notes=notes)

    def to_notes(self) -> list[dict]:
        return [note.model_dump(mode="json", exclude_none=True) for note in self.notes]
