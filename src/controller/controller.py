from fastapi import APIRouter, Depends
from core.container import agent_service
from controller.models import ChatRequest, ChatResponse

from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName
from service.agent_service import AgentService

router = APIRouter()

URI_CHAT_PREFIX = "/chat"
URI_MODELS = f"{URI_CHAT_PREFIX}/models"
URI_PING_CHAT = f"{URI_CHAT_PREFIX}/ping"


@router.get(URI_MODELS)
def get_models() -> list[ChatModelName]:
    """List the supported chat model identifiers."""
    return list(ChatModelName)


@router.post(URI_PING_CHAT)
def ping_chat(request: ChatRequest, service: AgentService = Depends(agent_service)) -> ChatResponse:
    chat_response = service.ping_chat(model=request.model, temperature=request.temperature, message=request.message)
    text = getattr(chat_response.response_schema, "response", None)
    if text is None:
        text = str(chat_response.raw.content)
    return ChatResponse(
        response=text,
        input_tokens=chat_response.input_tokens,
        output_tokens=chat_response.output_tokens,
        total_tokens=chat_response.total_tokens,
        parsing_error=str(chat_response.parsing_error) if chat_response.parsing_error else None,
    )


URI_AGENT_PREFIX = "/agent"
URI_ROLES = f"{URI_AGENT_PREFIX}/roles"

@router.get(URI_ROLES)
def list_roles() -> list[AgentRole]:
    """List available agents."""
    return list(AgentRole)



