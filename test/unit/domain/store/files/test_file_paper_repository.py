"""Unit tests for the local files store (domain/store/files): FilePaperRepository
listing, safe id resolution, read, signature, save and delete over a real tmp
papers folder. Files are named by paper_id (``<paper-type>_<name>_<extension>``,
no dot-extension); the trailing ``_pdf``/``_txt`` segment encodes the format.
No other store involved."""
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
    (papers / "other_p_txt").write_text("content", encoding="utf-8")
    (papers / "other_q_pdf").write_bytes(b"%PDF-1.4 stub")
    (papers / "notes_md").write_text("ignored", encoding="utf-8")  # unsupported format
    monkeypatch.setattr(get_global_config(), "papers_dir", str(papers))
    return FilePaperRepository()


class TestReads:
    def test_list_filters_by_format_and_sorts(self, repo):
        assert [p.paper_id for p in repo.list()] == ["other_p_txt", "other_q_pdf"]  # notes_md excluded

    def test_list_returns_stored_papers(self, repo):
        papers = repo.list()
        assert all(isinstance(p, StoredPaper) for p in papers)
        first = next(p for p in papers if p.paper_id == "other_p_txt")
        assert first.size == len("content") and first.mtime_ns > 0

    def test_get_and_missing(self, repo):
        assert repo.get("other_p_txt").paper_id == "other_p_txt"
        assert repo.get("other_missing_txt") is None

    def test_exists(self, repo):
        assert repo.exists("other_p_txt") is True
        assert repo.exists("other_missing_txt") is False

    def test_read_text(self, repo):
        assert repo.read_text("other_p_txt") == "content"

    def test_signature(self, repo):
        sig = repo.signature("other_p_txt")
        assert isinstance(sig, RagFileSignature)
        assert sig.size == len("content") and sig.mtime_ns > 0

    def test_file_format_from_id(self, repo):
        assert repo.file_format("other_p_txt") == "txt"
        assert repo.file_format("other_q_pdf") == "pdf"


class TestResolve:
    def test_resolve_returns_absolute_path(self, repo):
        path = repo.resolve("other_p_txt")
        assert path.is_file() and path.name == "other_p_txt"

    def test_missing_raises_not_found(self, repo):
        with pytest.raises(NotFoundError):
            repo.resolve("other_missing_txt")

    def test_unsupported_format_raises(self, repo):
        with pytest.raises(ValidationError):
            repo.resolve("notes_md")

    def test_traversal_is_blocked(self, repo):
        with pytest.raises(ValidationError):
            repo.resolve("../secret_txt")


class TestWrites:
    def test_save_creates_file_and_returns_stored(self, repo):
        stored = repo.save("other_uploaded_txt", b"new paper")
        assert isinstance(stored, StoredPaper) and stored.paper_id == "other_uploaded_txt"
        assert repo.read_text("other_uploaded_txt") == "new paper"

    def test_save_rejects_unsupported_format(self, repo):
        with pytest.raises(ValidationError):
            repo.save("bad_md", b"x")

    def test_delete_removes_file(self, repo):
        repo.delete("other_p_txt")
        assert repo.get("other_p_txt") is None
