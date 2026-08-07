"""Typed value models for the Redis keyspaces: the RAG index (keyspace
rag-index), the cached OpenReview response (keyspace open-review-cache) and
the agent traces (keyspaces agent-trace / agent-context)."""
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RagFileSignature(BaseModel):
    """Metadata about a paper file, used to detect changes and avoid stale RAG indexes."""
    mtime_ns: int
    size: int


class RagIndexConfig(BaseModel):
    """The RAG index configuration used to build the index, stored with the index.
    ``strategy`` records which retrieval strategy built it (full_context / bm25 /
    embedding); kept as a plain string so the store shape stays decoupled."""
    strategy: str = "full_context"
    strategy_version: str = Field(min_length=1, max_length=100)


class RagSectionEntry(BaseModel):
    """One paper section (raw Docling heading) with its full body text. The whole
    paper is reassembled from these at run time (full-context pipeline)."""
    name: str
    text: str


class RagChunk(BaseModel):
    """One retrievable chunk (chunk-based strategies), tagged with its source
    section. ``embedding`` is stored only for the embedding strategy."""
    text: str
    section: str | None = None
    embedding: list[float] | None = None


class RagTokenUsage(BaseModel):
    """Token usage of the LLM call that built the index (summary strategy only)."""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class RagIndex(BaseModel):
    """The stored RAG index for one paper (suffix = doc id). Holds ``sections``
    (full_context) or ``chunks`` (bm25 / embedding) depending on the strategy;
    ``token_usage`` records the build cost when an LLM was involved (summary)."""
    doc_id: str
    paper_id: str
    file_signature: RagFileSignature
    settings: RagIndexConfig
    sections: list[RagSectionEntry] = Field(default_factory=list)
    chunks: list[RagChunk] = Field(default_factory=list)
    token_usage: RagTokenUsage | None = None


class ToolCallEntry(BaseModel):
    """One executed tool round-trip stored with the trace (mirror of the domain
    ``ToolCallRecord``, kept as a store shape)."""
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: str = ""


class AgentTraceRecord(BaseModel):
    """The verbatim trace of one agent invocation. The context text is NOT
    stored inline: ``context_hash`` points into the shared agent-context
    keyspace (one blob per SHA-256, so identical contexts are stored once);
    the repository resolves it into ``context_used`` at read time and strips
    it before writing."""

    input_message: str | None = None
    system_prompt: str | None = None
    context_hash: str | None = None
    context_used: str | None = None
    response_payload: dict[str, Any] = Field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_seconds: float | None = None
    tool_trace: list[ToolCallEntry] | None = None


class AgentTraceBundle(BaseModel):
    """Every agent trace of one run, in invocation order (suffix = run_id).
    ``graph_review_agent.trace_index`` is the position in ``traces``."""

    run_id: str
    traces: list[AgentTraceRecord] = Field(default_factory=list)


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
