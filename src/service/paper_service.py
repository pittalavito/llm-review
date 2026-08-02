from domain.client.openreview import NotesAdapter
from models.domain.openreview import OpenReviewCache
from models.domain.paper import Author, CreateOpenReviewPaperRequest, Paper, PaperType

from service.store_service import StoreService


class PaperService:
    """Paper-catalog feature service: the /paper endpoints talk to this layer,
    which fronts the StoreService persistence (rows, files, authors) and owns
    the OpenReview-based creation (FE-provided PDF + notes cache)."""

    def __init__(self, store_service: StoreService):
        self._store_service = store_service

    def list_paper_types(self) -> list[PaperType]:
        """List the supported paper types."""
        return list(PaperType)

    def list_papers(self) -> list[Paper]:
        """The paper catalog — DB rows only."""
        return self._store_service.list_papers_catalog()

    def get_paper(self, paper_id: str) -> Paper | None:
        return self._store_service.get_paper(paper_id)

    def save_paper(self, paper: Paper, data: bytes, authors: list[Author] | None = None) -> Paper | None:
        """Create the catalog row, store the file and link the authors.
        None when a paper with the same id already exists."""
        return self._store_service.save_paper(paper, data, authors=authors)

    def get_paper_authors(self, paper_id: str) -> list[Author]:
        """The paper's authors with their positions, ordered by position."""
        return self._store_service.get_paper_authors(paper_id)

    # ------------------------------------------------------------------
    # OpenReview-based creation

    def create_from_openreview(self, request: CreateOpenReviewPaperRequest) -> Paper | None:
        """Create a paper from an OpenReview forum: everything (metadata,
        authors, decision, PDF bytes) arrives ready from the FE — here we only
        detect the API version from the forum note, save row+file+authors and
        cache the verbatim notes under the paper_id (for the comparator).
        None when a paper with the same id already exists."""
        forum_note = NotesAdapter.forum_note(request.forum_id, request.notes)
        api_version = NotesAdapter.api_version(forum_note)

        paper = Paper.from_paper(request, api_version)
        saved = self._store_service.save_paper(paper, request.file_bytes, authors=request.authors)
        if saved is None:
            return None

        self._store_service.save_open_review_cache(saved.paper_id, OpenReviewCache.from_notes(request.notes))
        return saved
