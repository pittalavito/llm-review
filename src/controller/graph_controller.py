"""Review-graph endpoints — everything under /graph."""
from fastapi import APIRouter, Depends, HTTPException

from core.container import graph_service, store_service

from models.controller.graph import GraphReviewConfigResponse, GraphReviewRecordResponse, GraphReviewSummaryResponse, CreateGraphReviewRequest

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
    
    req = CreateGraphReviewRequest.from_domain(request)
    config = service.compile(req)
    return GraphReviewConfigResponse.from_response(config)


@router.post("/invoke")
def invoke(request: CreateGraphReviewRequest, service: GraphReviewService = Depends(graph_service)) -> GraphReviewRecordResponse:
    """Run the compiled review graph and persist the run; 409-free by design:
    compile() is expected first (invoke fails with 500 otherwise)."""
    req = CreateGraphReviewRequest.from_domain(request)
    record = service.invoke(req)
    return GraphReviewRecordResponse.from_response(record)


@router.get("/runs")
def list_summary_runs(service: StoreService = Depends(store_service)) -> GraphReviewSummaryResponse:
    """Run history — lightweight summaries of every review-graph execution."""
    result = service.list_runs()
    return GraphReviewSummaryResponse.from_response(result)


@router.get("/runs/{run_id}")
def get_run(run_id: str, service: StoreService = Depends(store_service)) -> GraphReviewRecordResponse:
    """One full run: the record rebuilt from the agent traces, agent_records
    included — the data behind the FE run-flow view."""
    record = service.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return GraphReviewRecordResponse.from_response(record)