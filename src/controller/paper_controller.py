"""Paper catalog endpoints — everything under /paper."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.container import paper_service, retrieval_service

from models.controller.paper import CreateOpenReviewPaperRequest, CreatePaperRequest, CreatePaperResponse, PaperListResponse
from models.domain.paper import PaperType

from service.paper_service import PaperService
from service.retrieval_service import RetrievalService

router = APIRouter(prefix="/paper", tags=["paper"])


@router.get("/types")
def get_paper_types(service: PaperService = Depends(paper_service)) -> list[PaperType]:
    """List the supported paper types."""
    return service.list_paper_types()


@router.get("/list")
def list_papers(service: PaperService = Depends(paper_service)) -> PaperListResponse:
    """The paper catalog — DB rows only (no files-store or index data)."""
    papers = service.list_papers()
    return PaperListResponse.from_response(papers)


@router.post("/create-openreview")
def create_openreview_paper(request: CreateOpenReviewPaperRequest, service: PaperService = Depends(paper_service)) -> CreatePaperResponse:
    """Create a paper from an OpenReview forum (conference + forum id + pasted
    notes): metadata, authors and the notes cache come from the request; the
    PDF is fetched from the uri inside the forum note. Not implemented in the
    service layer yet."""
    raise HTTPException(status_code=501, detail="OpenReview paper creation is not implemented yet.")


@router.post("/create")
def create_paper(
    request: CreatePaperRequest,
    background_tasks: BackgroundTasks,
    paper_service: PaperService = Depends(paper_service),
    retrieval_service: RetrievalService = Depends(retrieval_service),
) -> CreatePaperResponse:
    """Save the paper (row + file) and kick off the default full-context
    indexing in background — the response does not wait for it."""
    saved = paper_service.save_paper(request.paper, request.file_bytes, authors=request.authors)
    if saved is None:
        raise HTTPException(status_code=409, detail="A paper with this id already exists.")
    background_tasks.add_task(retrieval_service.multi_strategy_indexed, saved.paper_id)
    return CreatePaperResponse.from_response(saved)
