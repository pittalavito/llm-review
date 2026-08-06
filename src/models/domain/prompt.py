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
    VENUE = "venue"
    CALIBRATION = "calibration"
    
    
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
    run_id: str | None = None
    """Anchor to the graph run the instruction was derived from."""
    created_at: str
    is_active: bool = True


class SystemPromptPreset(BaseModel):
    """Domain model for a named per-role system-prompt preset: a bundle of
    (base prompt version label + instruction ids). ``(agent_role, name)`` is
    the natural key. Unlike versions/instructions a preset is a mutable
    selection. The persistence shape lives in
    models.store.db.SystemPromptPresetTable."""

    id: int
    agent_role: str
    name: str
    description: str | None = None
    base_prompt_version: str
    instruction_ids: list[int] = []
    created_at: str
    updated_at: str | None = None
    is_active: bool = True