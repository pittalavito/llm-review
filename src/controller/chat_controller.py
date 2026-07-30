"""Chat endpoints — everything under /chat."""
from fastapi import APIRouter, Depends

from controller.models import ChatRequest, ChatResponse
from core.container import agent_service
from domain.models.chat import ChatModelName
from service.agent_service import AgentService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models")
def get_models() -> list[ChatModelName]:
    """List the supported chat model identifiers."""
    return list(ChatModelName)


@router.post("/ping")
def ping_chat(request: ChatRequest, service: AgentService = Depends(agent_service)) -> ChatResponse:
    chat_response = service.ping_chat(model=request.model, temperature=request.temperature, message=request.message)
    text = getattr(chat_response.response_schema, "response", None)
    return ChatResponse(
        response=text,
        input_tokens=chat_response.input_tokens,
        output_tokens=chat_response.output_tokens,
        total_tokens=chat_response.total_tokens,
        parsing_error=str(chat_response.parsing_error) if chat_response.parsing_error else None,
    )
