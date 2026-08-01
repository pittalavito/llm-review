from enum import StrEnum
from pydantic import BaseModel


class PaperType(StrEnum):
    OPEN_REVIEW = "OPEN_REVIEW"
    OTHER = "OTHER"
    

class Author(BaseModel):
    """Domain/response model for a paper author. ``position`` is the author's
    1-based slot in a specific paper's author list (None outside that context)."""
    id: int | None = None
    full_name: str
    email: str | None = None
    affiliation: str | None = None
    openreview_profile_id: str | None = None
    position: int | None = None


class Paper(BaseModel):
    """Domain/response model for a catalog paper."""
    id: int | None = None
    paper_id: str
    paper_name: str
    paper_type: PaperType
    description: str | None = None
    open_review_id: str | None = None
    conference: str | None = None
    openreview_api_version: str | None = None
    human_decision: str | None = None
    num_graph_review: int = 0
