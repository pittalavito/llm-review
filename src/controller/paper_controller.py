"""Paper catalog endpoints — everything under /paper."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.container import retrieval_service, store_service
from models.controller.paper import CreatePaperRequest, CreatePaperResponse, PaperListResponse
from models.domain.paper import PaperType
from service.retrieval_service import RetrievalService
from service.store_service import StoreService

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/types")
def get_paper_types() -> list[PaperType]:
    """List the supported paper types."""
    return list(PaperType)


@router.get("/list")
def list_papers(service: StoreService = Depends(store_service)) -> PaperListResponse:
    """The paper catalog — DB rows only (no files-store or index data)."""
    papers = service.list_papers_catalog()
    return PaperListResponse.from_response(papers)


@router.post("/create")
def create_paper(
    request: CreatePaperRequest,
    background_tasks: BackgroundTasks,
    service: StoreService = Depends(store_service),
    retrieval: RetrievalService = Depends(retrieval_service),
) -> CreatePaperResponse:
    """Save the paper (row + file) and kick off the default full-context
    indexing in background — the response does not wait for it."""
    saved = service.save_paper(request.paper, request.file_bytes)
    if saved is None:
        raise HTTPException(status_code=409, detail="A paper with this id already exists.")
    background_tasks.add_task(retrieval.multi_strategy_indexed, saved.paper_id)
    return CreatePaperResponse.from_response(saved)
