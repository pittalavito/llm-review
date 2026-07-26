"""Domain models for retrieval: the RAG index (a domain replica of the stored
``domain.store.redis.models.RagIndex`` record — same shape, converted by
deserialization) and the lightweight ``IndexInfo`` metadata derived from it."""
from pydantic import BaseModel, Field


class RagFileSignature(BaseModel):
    """Metadata about a paper file, used to detect changes and avoid stale indexes."""
    mtime_ns: int
    size: int


class RagIndexConfig(BaseModel):
    """The RAG index configuration used to build the index."""
    strategy_version: str = Field(min_length=1, max_length=100)


class RagSectionEntry(BaseModel):
    """One paper section (raw Docling heading) with its full body text."""
    name: str
    text: str


class RagIndex(BaseModel):
    """The RAG index for one paper (domain replica of the stored record)."""
    doc_id: str
    paper_path: str
    file_signature: RagFileSignature
    settings: RagIndexConfig
    sections: list[RagSectionEntry] = Field(default_factory=list)


class IndexInfo(BaseModel):
    """Lightweight metadata about a paper's RAG index (no section text)."""
    doc_id: str
    paper_path: str
    section_count: int
