"""Domain models parsed from the OpenReview cache: the structured human
reviewer reviews and the human meta-review (area chair). Built by the store
Adapter from the raw cached notes; used by the comparison feature."""
from pydantic import BaseModel


class HumanReview(BaseModel):
    """A human reviewer's review, parsed from one OpenReview 'official review' note."""
    note_id: str
    reviewer_id: str
    summary: str | None = None
    strengths: str | None = None
    weaknesses: str | None = None
    full_text: str | None = None
    rating: int | None = None
    rating_label: str | None = None
    confidence: int | None = None
    confidence_label: str | None = None
    questions: str | None = None


class HumanMetaReview(BaseModel):
    """A human meta-review (area chair), parsed from one OpenReview 'meta review' note."""
    note_id: str
    text: str | None = None
    recommendation: str | None = None
