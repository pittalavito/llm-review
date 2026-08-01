from enum import StrEnum
from pydantic import BaseModel


class PromptVersion(BaseModel):
    """Domain model for a registered prompt-template version. The persistence
    shape lives in models.store.db.PromptVersionTable; the repository maps rows to this
    plain model so the SQL table class never leaks past the domain boundary."""

    id: int
    agent_role: str
    version_label: str
    template: str
    template_hash: str
    description: str | None = None
    created_at: str
    is_active: bool = True
    
    
class InstructionType(StrEnum):
    INTENTION = "intention"
    KNOWLEDGEABILITY = "knowledgeability"
    COMMITMENT = "commitment"
    FOCUS = "focus"
    
    
class PromptInstruction(BaseModel):
    """Domain model for a registered prompt instruction. ``(type, label)`` is
    the natural key (the ids carried by AgentSystemPromptRequest are labels).
    The persistence shape lives in models.store.db.PromptInstructionTable; the
    repository maps rows to this plain model so the SQL table class never leaks
    past the domain boundary."""
    id: int
    type: InstructionType | None = None
    label: str
    instruction: str
    description: str | None = None
    agent_role: str | None = None
    created_at: str
    is_active: bool = True