"""Local filesystem store for the paper files under ``config.papers_dir`` — the
single source of physical access to the papers (list, read, signature, save,
delete) and the only layer that knows about file paths.

Every file is stored flat under the root with the ``paper_id``
(``<paper-type>_<name>_<extension>``) as its file name: callers pass ids, never
paths. The trailing ``_pdf`` / ``_txt`` segment of the id encodes the format,
replacing the old dot-extension checks.
"""
from __future__ import annotations

import re
from pathlib import Path

from config import get_global_config
from core.error import NotFoundError, ValidationError
from domain.models.retrieval import RagFileSignature
from domain.store.files.models import StoredPaper
from domain.store.files.repository import FileStore

_PAPER_FORMAT_RE = re.compile(r"[-_](pdf|txt)$")


class FilePaperRepository(FileStore):
    """Paper files under the papers root, one flat file per ``paper_id``."""

    def __init__(self):
        super().__init__(Path(get_global_config().papers_dir))

    # ------------------------------------------------------------------ reads
    def list(self) -> list[StoredPaper]:
        return [
            self._to_stored(path)
            for path in sorted(self.root.iterdir())
            if path.is_file() and _PAPER_FORMAT_RE.search(path.name)
        ]

    def get(self, paper_id: str) -> StoredPaper | None:
        path = self._safe_path(paper_id)
        return self._to_stored(path) if path.is_file() else None

    def exists(self, paper_id: str) -> bool:
        return self._safe_path(paper_id).is_file()

    def resolve(self, paper_id: str) -> Path:
        """Absolute path of the paper file. Raises if the file is missing or the
        id does not encode a supported format."""
        self.file_format(paper_id)
        path = self._safe_path(paper_id)
        if not path.is_file():
            raise NotFoundError(f"Paper file not found: {paper_id}")
        return path

    def read_bytes(self, paper_id: str) -> bytes:
        return self.resolve(paper_id).read_bytes()

    def read_text(self, paper_id: str) -> str:
        return self.resolve(paper_id).read_text(encoding="utf-8")

    def signature(self, paper_id: str) -> RagFileSignature:
        stat = self.resolve(paper_id).stat()
        return RagFileSignature(mtime_ns=stat.st_mtime_ns, size=stat.st_size)

    @staticmethod
    def file_format(paper_id: str) -> str:
        """File format ("pdf" | "txt") encoded in the id's trailing segment."""
        match = _PAPER_FORMAT_RE.search(paper_id)
        if match is None:
            raise ValidationError("Unsupported file type. Use .txt or .pdf files.")
        return match.group(1)

    # ----------------------------------------------------------------- writes
    def save(self, paper_id: str, data: bytes) -> StoredPaper:
        """Store the file under the root with ``paper_id`` as its name."""
        self.file_format(paper_id)
        path = self._safe_path(paper_id)
        path.write_bytes(data)
        return self._to_stored(path)

    def delete(self, paper_id: str) -> None:
        self.resolve(paper_id).unlink()

    # ----------------------------------------------------------------- helper
    def _to_stored(self, path: Path) -> StoredPaper:
        stat = path.stat()
        return StoredPaper(paper_id=self._relative(path), size=stat.st_size, mtime_ns=stat.st_mtime_ns)
