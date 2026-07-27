"""Local filesystem store for the paper files under ``config.papers_dir`` — the
single source of physical access to the papers (list, read, signature, save,
delete). The DB catalog is seeded from this list; retrieval reads/parses from it.
"""
from __future__ import annotations

from pathlib import Path

from config import get_global_config
from core.error import NotFoundError, ValidationError
from domain.models.retrieval import RagFileSignature
from domain.store.files.models import StoredPaper
from domain.store.files.repository import FileStore

_PAPER_EXTENSIONS = {".pdf", ".txt"}


class FilePaperRepository(FileStore):
    """Paper files under the papers root. ``relative_path`` (posix) is the id."""

    def __init__(self):
        super().__init__(Path(get_global_config().papers_dir))

    # ------------------------------------------------------------------ reads
    def list(self) -> list[StoredPaper]:
        return [
            self._to_stored(path)
            for path in sorted(self.root.rglob("*"))
            if path.is_file() and path.suffix.lower() in _PAPER_EXTENSIONS
        ]

    def list_paths(self) -> list[str]:
        return [paper.relative_path for paper in self.list()]

    def get(self, relative_path: str) -> StoredPaper | None:
        path = self._safe_path(relative_path)
        return self._to_stored(path) if path.is_file() else None

    def exists(self, relative_path: str) -> bool:
        return self._safe_path(relative_path).is_file()

    def resolve(self, relative_path: str) -> tuple[Path, str]:
        """Absolute path + canonical relative path. Raises if the file is missing
        or has an unsupported extension."""
        path = self._safe_path(relative_path)
        if not path.is_file():
            raise NotFoundError(f"Paper file not found: {relative_path}")
        if path.suffix.lower() not in _PAPER_EXTENSIONS:
            raise ValidationError("Unsupported file type. Use .txt or .pdf files.")
        return path, self._relative(path)

    def read_bytes(self, relative_path: str) -> bytes:
        return self.resolve(relative_path)[0].read_bytes()

    def read_text(self, relative_path: str) -> str:
        return self.resolve(relative_path)[0].read_text(encoding="utf-8")

    def signature(self, relative_path: str) -> RagFileSignature:
        stat = self.resolve(relative_path)[0].stat()
        return RagFileSignature(mtime_ns=stat.st_mtime_ns, size=stat.st_size)

    # ----------------------------------------------------------------- writes
    def save(self, relative_path: str, data: bytes) -> StoredPaper:
        path = self._safe_path(relative_path)
        if path.suffix.lower() not in _PAPER_EXTENSIONS:
            raise ValidationError("Unsupported file type. Use .txt or .pdf files.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self._to_stored(path)

    def delete(self, relative_path: str) -> None:
        self.resolve(relative_path)[0].unlink()

    # ----------------------------------------------------------------- helper
    def _to_stored(self, path: Path) -> StoredPaper:
        stat = path.stat()
        return StoredPaper(relative_path=self._relative(path), name=path.name, size=stat.st_size, mtime_ns=stat.st_mtime_ns)
