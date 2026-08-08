"""Unit tests for RetrievalService (service/retrieval_service.py). The StoreService
is an in-memory fake (holding domain RagIndex by doc_id) whose config points
papers_dir at a tmp folder with a real .txt paper — so no Redis, no torch, no
other real service is involved."""
import pytest

from config import get_global_config
from core.error import NotFoundError
from models.domain.agent import AgentRequestContext, AgentRole, ContextMode, CreateAgentRequest
from models.domain.chat import ChatModelName
from models.domain.retrieval import IndexInfo, RagStrategy, SummaryResult
from domain.retrieval.base import Summarizer
from domain.store.files.paper_repository import FilePaperRepository
from domain.store.redis.rag_index_repository import RedisRagIndexRepository
from service.chat_service import ChatService
from service.retrieval_service import RetrievalService


class FakeStoreService:
    """In-memory StoreService stand-in: only what RetrievalService needs.
    File access delegates to a real FilePaperRepository over the tmp papers
    folder, mirroring the facade methods of the real StoreService."""

    def __init__(self):
        self._papers_files = FilePaperRepository()
        self.store: dict = {}
        self.save_calls = 0

    @staticmethod
    def compute_doc_id(paper_id, strategy, strategy_version):
        return RedisRagIndexRepository.compute_doc_id(paper_id, strategy, strategy_version)

    def get_source_path_for_paper(self, paper_id):
        return self._papers_files.resolve(paper_id)

    def signature(self, paper_id):
        return self._papers_files.signature(paper_id)

    def file_format(self, paper_id):
        return self._papers_files.file_format(paper_id)

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
    # Pin the summarizer to the mock model: the config/.env default may point at
    # a real provider, and a unit test must never make a network call.
    monkeypatch.setattr(get_global_config(), "summarizer_model", "mock")
    store = FakeStoreService()
    return RetrievalService(store, ChatService()), store, papers


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


def _agent_request(context: AgentRequestContext) -> CreateAgentRequest:
    return CreateAgentRequest(
        paper_id="other_p_txt",
        model=ChatModelName.MOCK,
        temperature=0.4,
        agent_role=AgentRole.REVIEWER,
        prompt_preset_id=1,
        context=context,
    )


class TestGetAgentContext:
    def test_summary_mode_returns_the_cached_llm_summary(self, setup):
        """Default summarizer is the mock model: the summary is generated on
        first use (lazy), stored under the model-suffixed doc_id, and served
        from cache afterwards."""
        service, store, _ = setup
        request = _agent_request(AgentRequestContext(context_mode=ContextMode.SUMMARY))
        context = service.get_agent_context(request)
        assert context is not None and "[mock summary]" in context
        assert "other_p_txt+summary-v2-mock" in store.store
        usage = store.store["other_p_txt+summary-v2-mock"].token_usage
        assert usage is not None and usage.total_tokens and usage.total_tokens > 0  # build cost tracked on the index
        saves_after_first = store.save_calls
        assert service.get_agent_context(request) == context  # cache hit
        assert store.save_calls == saves_after_first  # not rebuilt

    def test_summary_cache_is_keyed_on_the_summarizer_model(self, setup, monkeypatch):
        """Changing the summarizer model changes the doc_id: the old summary is
        not served, a new one is generated and cached alongside it."""
        service, store, _ = setup
        request = _agent_request(AgentRequestContext(context_mode=ContextMode.SUMMARY))
        first = service.get_agent_context(request)

        class OtherSummarizer(Summarizer):
            def summarize(self, sections):
                return SummaryResult(summary="summary from the other model")

        monkeypatch.setattr(get_global_config(), "summarizer_model", "other-model")
        monkeypatch.setattr(service, "_summarizer", OtherSummarizer())
        second = service.get_agent_context(request)
        assert second == "summary from the other model" and second != first
        assert "other_p_txt+summary-v2-mock" in store.store  # both coexist
        assert "other_p_txt+summary-v2-other-model" in store.store

    def test_full_context_still_works(self, setup):
        service, _, _ = setup
        request = _agent_request(AgentRequestContext(context_mode=ContextMode.FULL_CONTEXT))
        context = service.get_agent_context(request)
        assert context is not None and "gradient descent" in context

    def test_tool_flag_does_not_change_context_resolution(self, setup):
        """use_retrieval_tool is config-only in this slice: it must not alter
        what get_agent_context returns for any mode."""
        service, _, _ = setup
        without_tool = service.get_agent_context(_agent_request(AgentRequestContext(context_mode=ContextMode.FULL_CONTEXT)))
        with_tool = service.get_agent_context(_agent_request(
            AgentRequestContext(context_mode=ContextMode.FULL_CONTEXT, use_retrieval_tool=True, retrieval_top_k=7),
        ))
        assert with_tool == without_tool
        assert service.get_agent_context(_agent_request(AgentRequestContext(context_mode=ContextMode.NONE, use_retrieval_tool=True))) is None


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

    def test_build_retrieval_tool_searches_the_paper(self, setup):
        """The tool closure retrieves BM25 passages from this paper's index,
        indexing it lazily on first call."""
        service, store, _ = setup
        retrieval_tool = service.build_retrieval_tool("other_p_txt", top_k=1)
        assert retrieval_tool.name == "search_paper"
        result = retrieval_tool.invoke({"query": "imagenet gradient"})
        assert "gradient descent" in result
        assert "other_p_txt+bm25-v3" in store.store  # built under the current version

    def test_multi_strategy_indexed_uses_the_current_versions(self, setup):
        """The agent-facing versions: full_context v2 (line-number filter), the
        chunk strategies v3 (chunker + tokens + references exclusion)."""
        service, store, _ = setup
        service.multi_strategy_indexed("other_p_txt")
        assert "other_p_txt+full_context-v2" in store.store
        assert "other_p_txt+bm25-v3" in store.store
        assert "other_p_txt+embedding-v3" in store.store

    def test_section_reuse_works_across_different_versions(self, setup, monkeypatch):
        """bm25 v2 must recycle the sections of the full_context v1 index (the
        lookup is pinned to full_context's own version, not the caller's)."""
        service, _, _ = setup
        calls = {"n": 0}
        original = service._reader.extract_structure

        def counting(source_path, file_format):
            calls["n"] += 1
            return original(source_path, file_format)

        monkeypatch.setattr(service._reader, "extract_structure", counting)
        service.multi_strategy_indexed("other_p_txt")
        assert calls["n"] == 1  # parsed once despite v1/v2 mix

    def test_chunk_strategies_reuse_full_context_sections(self, setup, monkeypatch):
        """bm25/embedding recycle the parsed sections of a fresh full-context
        index instead of re-running the (expensive) file parse."""
        service, _, _ = setup
        calls = {"n": 0}
        original = service._reader.extract_structure

        def counting(source_path, file_format):
            calls["n"] += 1
            return original(source_path, file_format)

        monkeypatch.setattr(service._reader, "extract_structure", counting)
        # Reuse is keyed on full_context's CURRENT version ("v2").
        service.index_paper("other_p_txt", RagStrategy.FULL_CONTEXT, "v2")
        service.index_paper("other_p_txt", RagStrategy.BM25, "v3")
        service.index_paper("other_p_txt", RagStrategy.EMBEDDING, "v3")
        assert calls["n"] == 1  # parsed once, reused twice

    def test_stale_full_context_sections_are_not_reused(self, setup, monkeypatch):
        """When the file changed after the full-context index, chunk strategies
        must re-parse instead of recycling stale sections."""
        service, _, papers = setup
        calls = {"n": 0}
        original = service._reader.extract_structure

        def counting(source_path, file_format):
            calls["n"] += 1
            return original(source_path, file_format)

        monkeypatch.setattr(service._reader, "extract_structure", counting)
        service.index_paper("other_p_txt", RagStrategy.FULL_CONTEXT, "v2")
        (papers / "other_p_txt").write_text("a brand new much longer body about transformers", encoding="utf-8")
        service.index_paper("other_p_txt", RagStrategy.BM25, "v3")
        assert calls["n"] == 2  # full-context sections were stale -> re-parsed

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
