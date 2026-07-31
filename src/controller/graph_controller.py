"""Review-graph endpoints — everything under /graph."""
from fastapi import APIRouter, Depends

from models.controller import CompileGraphResponse, CompiledAgentInfo
from core.container import graph_service, store_service
from models.domain.graph import CreateGraphReviewRequest
from models.domain.run_record import GraphReviewRecord, GraphReviewSummary
from service.graph_service import ReviewGraphService
from service.store_service import StoreService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/runs")
def list_graph_runs(service: StoreService = Depends(store_service)) -> list[GraphReviewSummary]:
    """Run history — lightweight summaries of every review-graph execution."""
    return service.list_runs()


@router.post("/compile")
def compile_graph(request: CreateGraphReviewRequest, service: ReviewGraphService = Depends(graph_service)) -> CompileGraphResponse:
    """Build the agents from the request's config and compile the review graph.
    Returns the compiled committee (Agent objects are not serializable)."""
    agents = service.compile(request)
    return CompileGraphResponse.from_agents(agents)


@router.post("/invoke")
def invoke_graph(request: CreateGraphReviewRequest, service: ReviewGraphService = Depends(graph_service)) -> GraphReviewRecord:
    """Run the compiled review graph and persist the run; 409-free by design:
    compile() is expected first (invoke fails with 500 otherwise)."""
    return service.invoke(request)