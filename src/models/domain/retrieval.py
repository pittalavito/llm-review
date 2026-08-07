"""Domain models for retrieval: the RAG index (a domain replica of the stored
``models.store.redis.RagIndex`` record — same shape, converted by
deserialization) and the lightweight ``IndexInfo`` metadata derived from it.

An index is strategy-specific: the full-context strategy fills ``sections``, the
chunk-based strategies (bm25, embedding) fill ``chunks`` — ``settings.strategy``
records which one built it."""
from enum import StrEnum

from pydantic import BaseModel, Field


class RagStrategy(StrEnum):
    """The retrieval strategy that built / serves an index."""
    FULL_CONTEXT = "full_context"
    """Whole paper, all sections concatenated — no query."""
    BM25 = "bm25"
    """Chunk the paper, rank chunks by BM25 lexical score against the query."""
    EMBEDDING = "embedding"
    """Chunk the paper, rank chunks by embedding cosine similarity to the query."""
    SUMMARY = "summary"
    """One LLM-generated summary of the whole paper — no query."""


class RagFileSignature(BaseModel):
    """Metadata about a paper file, used to detect changes and avoid stale indexes."""
    mtime_ns: int
    size: int


class RagIndexConfig(BaseModel):
    """The RAG index configuration used to build the index."""
    strategy: RagStrategy = RagStrategy.FULL_CONTEXT
    strategy_version: str = Field(min_length=1, max_length=100)


class RagTokenUsage(BaseModel):
    """Token usage of the LLM call that built an index (summary strategy only —
    the other strategies cost no tokens)."""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class SummaryResult(BaseModel):
    """What a Summarizer returns: the summary text plus the token usage of the
    LLM call that produced it (None for token-free summarizers, e.g. fakes)."""
    summary: str
    token_usage: RagTokenUsage | None = None


class RagSectionEntry(BaseModel):
    """One paper section (raw Docling heading) with its full body text."""
    name: str
    text: str


class RagChunk(BaseModel):
    """One retrievable chunk (chunk-based strategies), tagged with its source
    section. ``embedding`` is populated only by the embedding strategy."""
    text: str
    section: str | None = None
    embedding: list[float] | None = None


class RagIndex(BaseModel):
    """The RAG index for one paper (domain replica of the stored record)."""
    doc_id: str
    paper_id: str
    file_signature: RagFileSignature
    settings: RagIndexConfig
    sections: list[RagSectionEntry] = Field(default_factory=list)
    chunks: list[RagChunk] = Field(default_factory=list)
    token_usage: RagTokenUsage | None = None
    """Cost of building the index, when an LLM was involved (summary strategy)."""


class IndexInfo(BaseModel):
    """Lightweight metadata about a paper's RAG index (no section/chunk text)."""
    doc_id: str
    paper_id: str
    section_count: int
    token_usage: RagTokenUsage | None = None
