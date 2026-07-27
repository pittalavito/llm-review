from fastapi import APIRouter, Depends
from core.container import agent_service
from controller.models import ChatRequest

from domain.models.agent import AgentRole
from service.agent_service import AgentService

router = APIRouter()

URI_PREFIX = "/agent"
URI_ROLES = f"{URI_PREFIX}/roles"
URI_CHAT = f"{URI_PREFIX}/ping_chat"


@router.get(URI_ROLES)
def list_roles() -> list[AgentRole]:
    """List available agents."""
    return list(AgentRole)


@router.post(URI_CHAT)
def ping_chat(request: ChatRequest, service: AgentService = Depends(agent_service)):
    chat_response = service.ping_chat(model=request.model, temperature=request.temperature, message=request.message)
    return chat_response

