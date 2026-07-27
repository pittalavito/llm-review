"""Unit tests for the local files store (domain/store/files): FilePaperRepository
listing, safe path resolution, read, signature, save and delete over a real tmp
papers folder. No other store involved."""
import pytest

from config import get_global_config
from core.error import NotFoundError, ValidationError
from domain.models.retrieval import RagFileSignature
from domain.store.files.models import StoredPaper
from domain.store.files.paper_repository import FilePaperRepository


@pytest.fixture
def repo(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "p.txt").write_text("content", encoding="utf-8")
    (papers / "sub").mkdir()
    (papers / "sub" / "q.pdf").write_bytes(b"%PDF-1.4 stub")
    (papers / "notes.md").write_text("ignored", encoding="utf-8")  # unsupported ext
    monkeypatch.setattr(get_global_config(), "papers_dir", str(papers))
    return FilePaperRepository()


class TestReads:
    def test_list_paths_recursive_filtered_sorted(self, repo):
        assert repo.list_paths() == ["p.txt", "sub/q.pdf"]  # .md excluded

    def test_list_returns_stored_papers(self, repo):
        papers = repo.list()
        assert all(isinstance(p, StoredPaper) for p in papers)
        first = next(p for p in papers if p.relative_path == "p.txt")
        assert first.name == "p.txt" and first.size == len("content") and first.mtime_ns > 0

    def test_get_and_missing(self, repo):
        assert repo.get("p.txt").relative_path == "p.txt"
        assert repo.get("missing.txt") is None

    def test_exists(self, repo):
        assert repo.exists("p.txt") is True
        assert repo.exists("missing.txt") is False

    def test_read_text(self, repo):
        assert repo.read_text("p.txt") == "content"

    def test_signature(self, repo):
        sig = repo.signature("p.txt")
        assert isinstance(sig, RagFileSignature)
        assert sig.size == len("content") and sig.mtime_ns > 0


class TestResolve:
    def test_resolve_returns_path_and_relative(self, repo):
        path, relative = repo.resolve("p.txt")
        assert path.is_file() and relative == "p.txt"

    def test_missing_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.resolve("missing.txt")

    def test_unsupported_extension_raises(self, repo):
        with pytest.raises(ValidationError):
            repo.resolve("notes.md")

    def test_traversal_is_blocked(self, repo):
        with pytest.raises(ValidationError):
            repo.resolve("../secret.txt")


class TestWrites:
    def test_save_creates_file_and_returns_stored(self, repo):
        stored = repo.save("uploaded.txt", b"new paper")
        assert isinstance(stored, StoredPaper) and stored.relative_path == "uploaded.txt"
        assert repo.read_text("uploaded.txt") == "new paper"

    def test_save_rejects_unsupported_extension(self, repo):
        with pytest.raises(ValidationError):
            repo.save("bad.md", b"x")

    def test_delete_removes_file(self, repo):
        repo.delete("p.txt")
        assert repo.get("p.txt") is None
