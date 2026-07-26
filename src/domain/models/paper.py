from enum import StrEnum

from pydantic import BaseModel


class PaperType(StrEnum):
    OPEN_REVIEW = "OPEN_REVIEW"
    OTHER = "OTHER"


class Paper(BaseModel):
    """Domain/response model for a catalog paper."""
    id: int | None = None
    paper_path: str
    paper_name: str
    paper_type: PaperType
    open_review_id: str | None = None
    conference: str | None = None
    openreview_api_version: str | None = None
    human_decision: str | None = None
    num_app_review: int = 0

