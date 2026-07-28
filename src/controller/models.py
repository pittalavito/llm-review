from pydantic import BaseModel, Field
from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName

class ChatRequest(BaseModel):
    """Basic chat request: model, temperature and the message — nothing else."""
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    message: str = "Respond with a simple 'ping' message."

class ChatResponse(BaseModel):
    """Full chat response returned to the FE as JSON: the model's message plus
    the token usage and any structured-output parsing error."""
    response: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    parsing_error: str | None = None