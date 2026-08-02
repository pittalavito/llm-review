from models.domain.paper import Author, Paper, PaperType

from service.store_service import StoreService


class PaperService:
    """Paper-catalog feature service: the /paper endpoints talk to this layer,
    which fronts the StoreService persistence (rows, files, authors). The
    OpenReview-based creation lands here too."""

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
