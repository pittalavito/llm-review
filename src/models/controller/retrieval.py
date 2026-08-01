"""Request/response models for the /retrieval endpoints."""
from pydantic import BaseModel

from models.domain.retrieval import IndexInfo, RagStrategy


class IndexPaperRequest(BaseModel):
    """Request model for indexing a paper for retrieval."""
    paper_id: str
    strategy: RagStrategy
    strategy_version: str = "v1"
    force: bool = False


class IndexPaperAccepted(BaseModel):
    """202 response: the indexing runs in background; poll the status endpoint
    with the same (paper_id, strategy, strategy_version) to know when done."""
    status: str = "accepted"
    paper_id: str
    strategy: RagStrategy
    strategy_version: str


class IndexStatusResponse(BaseModel):
    """Response containing the index metadata — ``index_info`` is None while
    the index is not built yet."""
    index_info: IndexInfo | None = None

    @classmethod
    def from_response(cls, index_info: IndexInfo | None) -> "IndexStatusResponse":
        """Construct an IndexStatusResponse from an IndexInfo (or None)."""
        return cls(index_info=index_info)
