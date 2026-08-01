"""Request/response models for the /paper endpoints."""
from pydantic import Base64Bytes, BaseModel, Field

from models.domain.paper import Paper


class CreatePaperRequest(BaseModel):
    """Request model for creating a new paper. ``file_bytes`` travels as a
    base64 string in the JSON body (raw bytes would not survive UTF-8) and is
    decoded to raw bytes by pydantic."""
    paper: Paper
    file_bytes: Base64Bytes = Field(..., description="The paper's file content, base64-encoded.")


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
