from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from config import get_config_with_secrets_masked
from core.container import agent_service, store_service, retrieval_service
from controller.models import ChatRequest, ChatResponse, CreatePaperRequest, IndexPaperAccepted, IndexPaperRequest
from core.error import NotFoundError

from domain.models.agent import AgentRole
from domain.models.chat import ChatModelName
from domain.models.paper import Paper, PaperType
from domain.models.retrieval import IndexInfo, RagStrategy
from domain.models.run_record import GraphReviewSummary

from service.agent_service import AgentService
from service.store_service import StoreService
from service.retrieval_service import RetrievalService

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
URI_PAPER_LIST = f"{URI_PAPER_PREFIX}/list"
URI_PAPER_TYPES = f"{URI_PAPER_PREFIX}/types"
URI_PAPER_CREATE = f"{URI_PAPER_PREFIX}/create"


@router.get(URI_PAPER_TYPES)
def get_paper_types() -> list[PaperType]:
    """List the supported paper types."""
    return list(PaperType)


@router.get(URI_PAPER_LIST)
def list_papers(service: StoreService = Depends(store_service)) -> list[Paper]:
    """The paper catalog — DB rows only (no files-store or index data)."""
    return service.list_papers_catalog()


@router.post(URI_PAPER_CREATE)
def create_paper(
    request: CreatePaperRequest,
    background_tasks: BackgroundTasks,
    service: StoreService = Depends(store_service),
    retrieval: RetrievalService = Depends(retrieval_service),
) -> Paper:
    """Save the paper (row + file) and kick off the default full-context
    indexing in background — the response does not wait for it."""
    saved = service.save_paper(request.paper, request.file_bytes)
    if saved is None:
        raise HTTPException(status_code=409, detail="A paper with this id already exists.")
    background_tasks.add_task(retrieval.multi_strategy_indexed, saved.paper_id)
    return saved


#####################################################################
#### Retrieval APIs #################################################
#####################################################################

URI_RETRIEVAL_PREFIX = "/retrieval"
URI_RETRIEVAL_STRATEGY_TYPES = f"{URI_RETRIEVAL_PREFIX}/strategy-types"
URI_RETRIEVAL_PAPER_INDEX = f"{URI_RETRIEVAL_PREFIX}/index"
URI_RETRIEVAL_PAPER_INDEX_STATUS = f"{URI_RETRIEVAL_PAPER_INDEX}/status"

@router.get(URI_RETRIEVAL_STRATEGY_TYPES)
def get_retrieval_strategy_types() -> list[RagStrategy]:
    """List the supported retrieval strategy types."""
    return list(RagStrategy)


@router.post(URI_RETRIEVAL_PAPER_INDEX, status_code=202)
def index_paper(
    request: IndexPaperRequest,
    background_tasks: BackgroundTasks,
    service: RetrievalService = Depends(retrieval_service),
) -> IndexPaperAccepted:
    try:
        service.store_service.signature(request.paper_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(service.index_paper, request.paper_id, request.strategy, request.strategy_version, force=request.force)
    return IndexPaperAccepted(paper_id=request.paper_id, strategy=request.strategy, strategy_version=request.strategy_version)


@router.get(URI_RETRIEVAL_PAPER_INDEX_STATUS)
def get_index_status(
    paper_id: str,
    strategy: RagStrategy,
    strategy_version: str = "v1",
    service: RetrievalService = Depends(retrieval_service),
) -> IndexInfo | None:
    """Lightweight status of an index: the IndexInfo when built, null otherwise."""
    return service.get_index_info(paper_id, strategy, strategy_version)


#####################################################################
#### Graph Review APIs ##############################################
#####################################################################

URI_GRAPH_PREFIX = "/graph"
URI_GRAPH_RUNS = f"{URI_GRAPH_PREFIX}/runs"


@router.get(URI_GRAPH_RUNS)
def list_graph_runs(service: StoreService = Depends(store_service)) -> list[GraphReviewSummary]:
    """Run history — lightweight summaries of every review-graph execution."""
    return service.list_runs()


# TODO Graph 1 # compile graph

# TODO Graph 2 # invoke graphs

# TODO Graph 4 # get graph run details

#####################################################################
#### Compare APIs ###################################################
#####################################################################