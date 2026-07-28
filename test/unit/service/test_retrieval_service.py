"""Unit tests for RetrievalService (service/retrieval_service.py). The StoreService
is an in-memory fake (holding domain RagIndex by doc_id) whose config points
papers_dir at a tmp folder with a real .txt paper — so no Redis, no torch, no
other real service is involved."""
import pytest

from config import get_global_config
from core.error import NotFoundError
from domain.models.retrieval import IndexInfo, RagStrategy
from domain.store.files.paper_repository import FilePaperRepository
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from service.retrieval_service import RetrievalService


class FakeStoreService:
    """In-memory StoreService stand-in: only what RetrievalService needs."""

    def __init__(self):
        self._papers_files = FilePaperRepository()
        self.store: dict = {}
        self.save_calls = 0

    @staticmethod
    def compute_doc_id(paper_id, strategy, strategy_version):
        return RedisRagIndexRepository.compute_doc_id(paper_id, strategy, strategy_version)

    def get_rag_index(self, doc_id):
        return self.store.get(doc_id)

    def save_rag_index(self, index):
        self.save_calls += 1
        self.store[index.doc_id] = index

    def list_indexed_papers(self) -> list[str]:
        return sorted({index.paper_id for index in self.store.values()})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    papers = tmp_path / "papers"
    papers.mkdir()
    (papers / "other_p_txt").write_text("gradient descent optimizes the model on imagenet", encoding="utf-8")
    monkeypatch.setattr(get_global_config(), "papers_dir", str(papers))
    store = FakeStoreService()
    return RetrievalService(store), store, papers


class TestRetrieveContext:
    def test_full_context_returns_the_paper(self, setup):
        service, _, _ = setup
        context = service.retrieve_context("other_p_txt", "ignored", RagStrategy.FULL_CONTEXT, "v1")
        assert context.startswith("# body")
        assert "gradient descent" in context

    def test_embedding_path_works_with_default_mock_embedder(self, setup):
        service, _, _ = setup
        context = service.retrieve_context("other_p_txt", "imagenet", RagStrategy.EMBEDDING, "v1")
        assert isinstance(context, str) and context

    def test_missing_paper_raises_not_found(self, setup):
        service, _, _ = setup
        with pytest.raises(NotFoundError):
            service.retrieve_context("other_nope_txt", "q", RagStrategy.FULL_CONTEXT, "v1")


class TestIndexing:
    def test_index_paper_persists_and_returns_info(self, setup):
        service, store, _ = setup
        info = service.index_paper("other_p_txt", RagStrategy.BM25, "v1")
        assert isinstance(info, IndexInfo)
        assert store.save_calls == 1
        assert "other_p_txt+bm25-v1" in store.store  # readable composite key

    def test_strategies_coexist_for_one_paper(self, setup):
        service, store, _ = setup
        service.index_paper("other_p_txt", RagStrategy.FULL_CONTEXT, "v1")
        service.index_paper("other_p_txt", RagStrategy.BM25, "v1")
        assert len(store.store) == 2  # no overwrite across strategies
        assert service.list_indexed() == ["other_p_txt"]  # listed once

    def test_uses_cache_then_rebuilds_when_file_changes(self, setup):
        service, store, papers = setup
        service.index_paper("other_p_txt", RagStrategy.FULL_CONTEXT, "v1")
        assert store.save_calls == 1

        service.retrieve_context("other_p_txt", "q", RagStrategy.FULL_CONTEXT, "v1")
        assert store.save_calls == 1  # cache hit — not rebuilt

        (papers / "other_p_txt").write_text("a much longer brand new body about transformers and attention", encoding="utf-8")
        context = service.retrieve_context("other_p_txt", "q", RagStrategy.FULL_CONTEXT, "v1")
        assert store.save_calls == 2  # file changed (size) -> rebuilt
        assert "transformers" in context
