from pydantic import BaseModel


class PromptVersion(BaseModel):
    """Domain model for a registered prompt-template version. The persistence
    shape lives in domain.store.db.models.PromptVersionTable; the repository maps rows to this
    plain model so the SQL table class never leaks past the domain boundary."""

    id: int
    agent_role: str
    version_label: str
    template: str
    template_hash: str
    description: str | None = None
    created_at: str
    is_active: bool = True
