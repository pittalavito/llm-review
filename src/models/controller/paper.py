"""Request/response models for the /paper endpoints."""
from pydantic import Base64Bytes, BaseModel, Field

from models.domain.paper import Author, Paper


class CreatePaperRequest(BaseModel):
    """Request model for creating a new paper. ``file_bytes`` travels as a
    base64 string in the JSON body (raw bytes would not survive UTF-8) and is
    decoded to raw bytes by pydantic. ``authors`` (optional) are linked to the
    paper in list order."""
    paper: Paper
    file_bytes: Base64Bytes = Field(..., description="The paper's file content, base64-encoded.")
    authors: list[Author] = []


class CreateOpenReviewPaperRequest(BaseModel):
    """Request model for creating a paper from an OpenReview forum: no file
    upload. The FE already parses the pasted ``GET /notes?forum=<forum_id>``
    response, so the extracted fields travel ready-to-use (paper_name, authors
    in order, human_decision) and the BE never re-derives them; ``notes`` stays
    the verbatim notes array (v1 or v2 shape) for the cache and the PDF uri."""
    conference: str
    forum_id: str
    paper_name: str
    authors: list[Author] = []
    human_decision: str | None = None
    description: str | None = None
    notes: list[dict]


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
