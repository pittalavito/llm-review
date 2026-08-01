"""Review-graph endpoints — everything under /graph."""
from fastapi import APIRouter, Depends

from core.container import graph_service, store_service

from models.domain.graph import CreateGraphReviewRequest
from models.domain.run_record import GraphReviewRecord, GraphReviewSummary

from models.controller.graph import GraphReviewConfigResponse, GraphReviewRecordResponse, GraphReviewSummaryResponse

from service.graph_service import GraphReviewService
from service.store_service import StoreService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/config")
def get_config(service: GraphReviewService = Depends(graph_service)) -> GraphReviewConfigResponse:
    """Return the current graph configuration."""
    config = service.get_config()
    return GraphReviewConfigResponse.from_response(config)

    
@router.post("/compile")
def compile(request: CreateGraphReviewRequest, service: GraphReviewService = Depends(graph_service)) -> GraphReviewConfigResponse:
    """Build the agents from the request's config and compile the review graph.
    Returns the compiled committee (Agent objects are not serializable)."""
    config = service.compile(request)
    return GraphReviewConfigResponse.from_response(config)


@router.post("/invoke")
def invoke(request: CreateGraphReviewRequest, service: GraphReviewService = Depends(graph_service)) -> GraphReviewRecordResponse:
    """Run the compiled review graph and persist the run; 409-free by design:
    compile() is expected first (invoke fails with 500 otherwise)."""
    record = service.invoke(request)
    return GraphReviewRecordResponse.from_response(record)


@router.get("/runs")
def list_summary_runs(service: StoreService = Depends(store_service)) -> GraphReviewSummaryResponse:
    """Run history — lightweight summaries of every review-graph execution."""
    result = service.list_runs()
    return GraphReviewSummaryResponse.from_response(result)