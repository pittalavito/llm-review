from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from core.container import agent_service
from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName
from service.agent_service import AgentService

router = APIRouter()

URI_PREFIX = "/agent"

URI_ROLES = f"{URI_PREFIX}/roles"
URI_CHAT = f"{URI_PREFIX}/chat"


class ChatRequest(BaseModel):
    """Basic chat request: model, temperature and the message — nothing else."""
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    message: str


class AgentRequest(BaseModel):
    """Request to create an agent with a specific role and chat client."""
    agent_role: AgentRole
    model: ChatModelName
    temperature: float = Field(default=0.0, ge=0, le=2)
    agent_index: int | None = None
    system_prompt: str = ""


@router.get(URI_ROLES)
def list_agents() -> list[AgentRole]:
    """List available agents."""
    return list(AgentRole)


@router.post(URI_CHAT)
def chat(request: ChatRequest, service: AgentService = Depends(agent_service)):
    chat = service._build_chat(model=request.model, temperature=request.temperature)
    return chat.invoke(request.message)
