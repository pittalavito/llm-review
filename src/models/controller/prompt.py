"""Request/response models for the /prompts endpoints."""
from pydantic import BaseModel

from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion


class CreatePromptRequest(BaseModel):
    """Request to register a new immutable prompt version."""
    agent_role: str
    version_label: str
    template: str
    description: str | None = None


class UpdatePromptRequest(BaseModel):
    """Versions are immutable: only description and is_active may change."""
    description: str | None = None
    is_active: bool | None = None


class PromptVersionResponse(BaseModel):
    """Response containing one prompt version."""
    prompt: PromptVersion

    @classmethod
    def from_response(cls, prompt: PromptVersion) -> "PromptVersionResponse":
        """Construct a PromptVersionResponse from a PromptVersion."""
        return cls(prompt=prompt)


class PromptVersionListResponse(BaseModel):
    """Response containing prompt versions from the registry."""
    prompts: list[PromptVersion]

    @classmethod
    def from_response(cls, prompts: list[PromptVersion]) -> "PromptVersionListResponse":
        """Construct a PromptVersionListResponse from a list of PromptVersion."""
        return cls(prompts=prompts)


class PromptPreviewRequest(BaseModel):
    """Request to compose the system prompt an agent would receive."""
    agent_role: str
    base_prompt_version: str
    instruction_labels: list[str] = []


class PromptPreviewResponse(BaseModel):
    """Response containing the composed system prompt."""
    prompt: str

    @classmethod
    def from_response(cls, prompt: str) -> "PromptPreviewResponse":
        """Construct a PromptPreviewResponse from the composed prompt string."""
        return cls(prompt=prompt)


class CreateInstructionRequest(BaseModel):
    """Request to register a new immutable persona instruction."""
    type: InstructionType
    label: str
    instruction: str
    description: str | None = None
    agent_role: str | None = None


class UpdateInstructionRequest(BaseModel):
    """Instructions are immutable: only description and is_active may change."""
    description: str | None = None
    is_active: bool | None = None


class PromptInstructionResponse(BaseModel):
    """Response containing one persona instruction."""
    instruction: PromptInstruction

    @classmethod
    def from_response(cls, instruction: PromptInstruction) -> "PromptInstructionResponse":
        """Construct a PromptInstructionResponse from a PromptInstruction."""
        return cls(instruction=instruction)


class PromptInstructionListResponse(BaseModel):
    """Response containing persona instructions from the registry."""
    instructions: list[PromptInstruction]

    @classmethod
    def from_response(cls, instructions: list[PromptInstruction]) -> "PromptInstructionListResponse":
        """Construct a PromptInstructionListResponse from a list of PromptInstruction."""
        return cls(instructions=instructions)
