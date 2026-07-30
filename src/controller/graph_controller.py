"""Review-graph endpoints — everything under /graph."""
from fastapi import APIRouter, Depends

from core.container import store_service
from domain.models.run_record import GraphReviewSummary
from service.store_service import StoreService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/runs")
def list_graph_runs(service: StoreService = Depends(store_service)) -> list[GraphReviewSummary]:
    """Run history — lightweight summaries of every review-graph execution."""
    return service.list_runs()


# TODO Graph 1 # compile graph

# TODO Graph 2 # invoke graphs

# TODO Graph 4 # get graph run details
