from enum import StrEnum
from pydantic import BaseModel
import re


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


class CreateOpenReviewPaperRequest(BaseModel):
    """Domain request to create a paper from an OpenReview forum. The FE has
    already parsed the pasted notes response: paper_name, authors (in order),
    human_decision and the PDF bytes arrive ready-to-use (openreview.net sits
    behind a bot challenge, so the browser fetches everything); ``notes`` is
    the verbatim notes array (v1 or v2 shape), kept for the cache."""
    conference: str
    forum_id: str
    paper_name: str
    file_bytes: bytes
    authors: list[Author] = []
    human_decision: str | None = None
    description: str | None = None
    notes: list[dict] = []


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
    
    @classmethod
    def from_paper(cls, request: CreateOpenReviewPaperRequest, openreview_api_version: str) -> "Paper":
        """Paper from an OpenReview create-request."""
        return cls(
            paper_id="",  # derived from paper_name by the store Factory
            paper_name=cls._to_file_name(request.paper_name),
            paper_type=PaperType.OPEN_REVIEW,
            description=request.description,
            open_review_id=request.forum_id,
            conference=request.conference,
            openreview_api_version=openreview_api_version,
            human_decision=request.human_decision,
        )
        
    @classmethod
    def _to_file_name(cls, paper_name: str) -> str:
        """Filename-safe ``<slug>.pdf`` from the FE-provided title — the store
        derives the paper_id (and the encoded format) from this name."""
        stem = re.sub(r"[^A-Za-z0-9]+", "_", paper_name).strip("_").lower() or "paper"
        return f"{stem[:80]}.pdf"
