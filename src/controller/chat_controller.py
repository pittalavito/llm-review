"""Chat endpoints — everything under /chat."""
from fastapi import APIRouter, Depends

from core.container import chat_service

from models.controller.chat import ChatRequest, ChatResponse

from service.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/models")
def get_models(service: ChatService = Depends(chat_service)) -> list[str]:
    """List the supported chat model identifiers."""
    return service.list_models()


@router.post("/ping")
def ping_chat(request: ChatRequest, service: ChatService = Depends(chat_service)) -> ChatResponse:
    chat_response = service.ping_chat(model=request.model, temperature=request.temperature, message=request.message)
    return ChatResponse.from_response(chat_response)
