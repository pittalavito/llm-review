"""Request/response models for the /chat endpoints."""
from pydantic import BaseModel, Field

from models.domain.chat import ChatModelName


class ChatRequest(BaseModel):
    """Basic chat request: model, temperature and the message — nothing else."""
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    message: str = "Respond with a simple 'ping' message."


class ChatResponse(BaseModel):
    """Full chat response returned to the FE as JSON: the model's payload
    (JSON-serialized) plus the token usage and any structured-output parsing
    error. ``response`` is None only when the invocation produced no payload."""
    response: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    parsing_error: str | None = None

    @classmethod
    def from_response(cls, chat_response) -> "ChatResponse":
        """Construct a ChatResponse from a domain ChatResponse."""
        return cls(
            response=getattr(chat_response.response_schema, "response", None),
            input_tokens=chat_response.input_tokens,
            output_tokens=chat_response.output_tokens,
            total_tokens=chat_response.total_tokens,
            parsing_error=str(chat_response.parsing_error) if chat_response.parsing_error else None,
        )
