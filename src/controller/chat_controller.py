"""Chat endpoints — everything under /chat."""
from fastapi import APIRouter, Depends

from models.controller.chat import ChatRequest, ChatResponse
from core.container import agent_service
from models.domain.chat import ChatModelName
from service.agent_service import AgentService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models")
def get_models() -> list[ChatModelName]:
    """List the supported chat model identifiers."""
    return list(ChatModelName)


@router.post("/ping")
def ping_chat(request: ChatRequest, service: AgentService = Depends(agent_service)) -> ChatResponse:
    chat_response = service.ping_chat(model=request.model, temperature=request.temperature, message=request.message)
    return ChatResponse.from_response(chat_response)
