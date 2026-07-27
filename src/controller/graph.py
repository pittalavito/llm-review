from fastapi import APIRouter, Depends
from core.container import to_implement
from models import ChatRequest

from domain.models.agent import AgentRole

router = APIRouter()

URI_PREFIX = "/graph"
URI_COMPILE = f"{URI_PREFIX}/compile"
URI_INVOKE = f"{URI_PREFIX}/invoke"

@router.post(URI_COMPILE)
def compile_graph(request: ChatRequest, service = Depends(to_implement)):
    chat = service._build_chat(model=request.model, temperature=request.temperature)
    return chat.invoke(request.message)


@router.post(URI_INVOKE)
def invoke_graph(request: ChatRequest, service = Depends(to_implement)):
    chat = service._build_chat(model=request.model, temperature=request.temperature)
    return chat.invoke(request.message)