from fastapi import APIRouter, Depends, HTTPException
from config import get_config_with_secrets_masked
from core.container import agent_service, store_service
from controller.models import ChatRequest, ChatResponse, CreatePaperRequest

from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName
from domain.models.paper import Paper, PaperType
from domain.models.retrieval import RagStrategy

from service.agent_service import AgentService
from service.store_service import StoreService

router = APIRouter()

#####################################################################
#### Admin APIs #####################################################
#####################################################################
URI_ADMIN_PREFIX = "/admin"
URI_ADMIN_CONFIG = f"{URI_ADMIN_PREFIX}/config"


@router.get(URI_ADMIN_CONFIG)
def get_config() -> dict:
    """The whole app config, with secrets masked: password/api-key fields
    become asterisks (empty ones stay empty) and credentials embedded in
    URLs (e.g. DATABASE_URL) are scrubbed."""
    return get_config_with_secrets_masked()


#####################################################################
#### Chat APIs ######################################################
#####################################################################
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
    return ChatResponse(
        response=text,
        input_tokens=chat_response.input_tokens,
        output_tokens=chat_response.output_tokens,
        total_tokens=chat_response.total_tokens,
        parsing_error=str(chat_response.parsing_error) if chat_response.parsing_error else None,
    )


#####################################################################
#### Agent APIs #####################################################
#####################################################################
URI_AGENT_PREFIX = "/agent"
URI_ROLES = f"{URI_AGENT_PREFIX}/roles"

@router.get(URI_ROLES)
def list_roles() -> list[AgentRole]:
    """List available agents."""
    return list(AgentRole)


#####################################################################
#### Paper APIs #####################################################
#####################################################################
URI_PAPER_PREFIX = "/paper"
URI_PAPER_TYPES = f"{URI_PAPER_PREFIX}/types"
URI_PAPER_CREATE = f"{URI_PAPER_PREFIX}/create"

@router.get(URI_PAPER_TYPES)
def get_paper_types() -> list[PaperType]:
    """List the supported paper types."""
    return list(PaperType)

# TODO Paper 2 # get paper by id


# TODO Paper 3 # get paper list da db 


@router.post(URI_PAPER_CREATE)
def create_paper(request: CreatePaperRequest, service: StoreService = Depends(store_service)) -> Paper:
    saved = service.save_paper(request.paper, request.file_bytes)
    if saved is None:
        raise HTTPException(status_code=409, detail="A paper with this id already exists.")
    return saved

#####################################################################
#### Retrieval APIs #################################################
#####################################################################
URI_RETRIEVAL_PREFIX = "/retrieval"
URI_RETRIEVAL_STRATEGY_TYPES = f"{URI_RETRIEVAL_PREFIX}/strategy-types"

@router.get(URI_RETRIEVAL_STRATEGY_TYPES)
def get_retrieval_strategy_types() -> list[RagStrategy]:
    """List the supported retrieval strategy types."""
    return list(RagStrategy)

# TODO Retrieval 2 # search paper

# TODO Retrieval 3 # index paper

# TODO Retrieval 4 # get indexed paper list

#####################################################################
#### Graph Review APIs ##############################################
#####################################################################

# TODO Graph 1 # compile graph

# TODO Graph 2 # invoke graph

# TODO Graph 3 # get graph run summary

# TODO Graph 4 # get graph run details

#####################################################################
#### Compare APIs ###################################################
#####################################################################