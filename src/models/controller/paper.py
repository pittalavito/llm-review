"""Request/response models for the /paper endpoints."""
from pydantic import Base64Bytes, BaseModel, Field

from models.domain.paper import Author, CreateOpenReviewPaperRequest as DomainCreateOpenReviewPaperRequest, Paper


class CreatePaperRequest(BaseModel):
    """Request model for creating a new paper. ``file_bytes`` travels as a
    base64 string in the JSON body (raw bytes would not survive UTF-8) and is
    decoded to raw bytes by pydantic. ``authors`` (optional) are linked to the
    paper in list order."""
    paper: Paper
    file_bytes: Base64Bytes = Field(..., description="The paper's file content, base64-encoded.")
    authors: list[Author] = []


class CreateOpenReviewPaperRequest(BaseModel):
    """Request model for creating a paper from an OpenReview forum. The FE
    already parses the pasted ``GET /notes?forum=<forum_id>`` response, so the
    extracted fields travel ready-to-use (paper_name, authors in order,
    human_decision) and the BE never re-derives them; the PDF travels base64 in
    ``file_bytes`` (downloaded by the user's browser — openreview.net blocks
    server-side fetches); ``notes`` stays the verbatim array for the cache."""
    conference: str
    forum_id: str
    paper_name: str
    file_bytes: Base64Bytes = Field(..., description="The paper's PDF content, base64-encoded.")
    authors: list[Author] = []
    human_decision: str | None = None
    description: str | None = None
    notes: list[dict]

    def to_domain(self) -> DomainCreateOpenReviewPaperRequest:
        """Controller request -> domain request (field-for-field)."""
        return DomainCreateOpenReviewPaperRequest.model_validate(self.model_dump())


class CreatePaperResponse(BaseModel):
    """Response containing the paper as saved in the catalog."""
    paper: Paper

    @classmethod
    def from_response(cls, paper: Paper) -> "CreatePaperResponse":
        """Construct a CreatePaperResponse from a Paper."""
        return cls(paper=paper)


class PaperListResponse(BaseModel):
    """Response containing the paper catalog."""
    papers: list[Paper]

    @classmethod
    def from_response(cls, papers: list[Paper]) -> "PaperListResponse":
        """Construct a PaperListResponse from a list of Paper."""
        return cls(papers=papers)
