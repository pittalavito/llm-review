"""Typed value models for the Redis keyspaces: the RAG index (keyspace
rag-index) and the cached OpenReview response (keyspace open-review-cache)."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RagFileSignature(BaseModel):
    """Metadata about a paper file, used to detect changes and avoid stale RAG indexes."""
    mtime_ns: int
    size: int


class RagIndexConfig(BaseModel):
    """The RAG index configuration used to build the index, stored with the index"""
    strategy_version: str = Field(min_length=1, max_length=100)


class RagSectionEntry(BaseModel):
    """One paper section (raw Docling heading) with its full body text. The whole
    paper is reassembled from these at run time (full-context pipeline)."""
    name: str
    text: str


class RagIndex(BaseModel):
    """The stored RAG index for one paper (suffix = doc id)."""
    doc_id: str
    paper_path: str
    file_signature: RagFileSignature
    settings: RagIndexConfig
    sections: list[RagSectionEntry] = Field(default_factory=list)


class OpenReviewCacheNote(BaseModel):
    """A single OpenReview note (one entry of a forum thread), as cached from the
    OpenReview API. Only the fields the pipeline reads are typed; everything else
    round-trips via extra="allow"."""

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
    """Cache of one paper's OpenReview response: the list of notes downloaded from
    the OpenReview API, re-fetched on a miss (suffix = paper filename stem)."""

    notes: list[OpenReviewCacheNote] = Field(default_factory=list)

    @classmethod
    def from_notes(cls, notes: list[dict]) -> "OpenReviewCache":
        return cls(notes=notes)

    def to_notes(self) -> list[dict]:
        return [note.model_dump(mode="json", exclude_none=True) for note in self.notes]
