"""Files store facade: one import point for the local filesystem store. Unlike
the db/redis stores there is no Adapter/Factory — ``StoredPaper`` is already the
domain shape, built directly by the repository."""
from models.store.files import StoredPaper
from domain.store.files.paper_repository import FilePaperRepository

__all__ = ["FilePaperRepository", "StoredPaper"]
