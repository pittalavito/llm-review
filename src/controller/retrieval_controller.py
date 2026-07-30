"""Retrieval/RAG endpoints — everything under /retrieval."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from controller.models import IndexPaperAccepted, IndexPaperRequest
from core.container import retrieval_service
from core.error import NotFoundError
from domain.models.retrieval import IndexInfo, RagStrategy
from service.retrieval_service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.get("/strategy-types")
def get_retrieval_strategy_types() -> list[RagStrategy]:
    """List the supported retrieval strategy types."""
    return list(RagStrategy)


@router.post("/index", status_code=202)
def index_paper(
    request: IndexPaperRequest,
    background_tasks: BackgroundTasks,
    service: RetrievalService = Depends(retrieval_service),
) -> IndexPaperAccepted:
    try:
        service._store_service.signature(request.paper_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(service.index_paper, request.paper_id, request.strategy, request.strategy_version, force=request.force)
    return IndexPaperAccepted(paper_id=request.paper_id, strategy=request.strategy, strategy_version=request.strategy_version)


@router.get("/index/status")
def get_index_status(
    paper_id: str,
    strategy: RagStrategy,
    strategy_version: str = "v1",
    service: RetrievalService = Depends(retrieval_service),
) -> IndexInfo | None:
    """Lightweight status of an index: the IndexInfo when built, null otherwise."""
    return service.get_index_info(paper_id, strategy, strategy_version)
