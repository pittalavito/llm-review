from pydantic import BaseModel, Field
from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName

class ChatRequest(BaseModel):
    """Basic chat request: model, temperature and the message — nothing else."""
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    message: str = "Respond with a simple 'ping' message."

class ChatResponse(BaseModel):
    """Basic chat response: the model's response message."""
    response: str