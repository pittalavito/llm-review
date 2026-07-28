from domain.retrieval.base import Embedder, MockEmbedder, PaperFileReader, RetrievalStrategy
from domain.store.redis.store import Adapter as RedisAdapter
from domain.models.agent import CreateAgentRequest, ContextMode
from domain.models.retrieval import IndexInfo, RagIndex, RagStrategy
from service.store_service import StoreService

MOCK_EMBEDD: Embedder = MockEmbedder()

class RetrievalService:

    def __init__(self, store_service: StoreService):
        self.store_service = store_service
        self._reader = PaperFileReader()
        self._embedder = MOCK_EMBEDD

    def get_agent_context(self, request: CreateAgentRequest) -> str | None:
        if request.context is None or request.context == ContextMode.NONE:
            return None
        if request.context == ContextMode.FULL_CONTEXT:
            return self.retrieve_context(paper_id=request.paper_id, query="", strategy=RagStrategy.FULL_CONTEXT, strategy_version="v1")
        if request.retrieval_context_query is None and request.context in (ContextMode.BM25, ContextMode.EMBEDDING):
            raise ValueError("retrieval_context_query must be provided for BM25 or EMBEDDING context modes.")
        strategy = RagStrategy(request.context)
        return self.retrieve_context(paper_id=request.paper_id, query=request.retrieval_context_query, strategy=strategy, strategy_version="v1")

    def retrieve_context(self, paper_id: str, query: str, strategy: RagStrategy, strategy_version: str) -> str:
        """Context text for ``query`` under ``strategy`` — indexing the paper first
        if there is no fresh index for this (paper, strategy, version)."""
        index = self._get_or_build(paper_id, strategy, strategy_version)
        return self._strategy(strategy, strategy_version).build_context(index, query)

    def index_paper(self, paper_id: str, strategy: RagStrategy, strategy_version: str, force: bool = False) -> IndexInfo:
        """Ensure the paper is indexed under (strategy, version); rebuild when the
        file changed or ``force``. Returns the lightweight index metadata."""
        index = self._get_or_build(paper_id, strategy, strategy_version, force=force)
        return RedisAdapter.to_index_info(index)

    def get_index(self, paper_id: str, strategy: RagStrategy, strategy_version: str) -> RagIndex | None:
        """The stored index for (paper, strategy, version), without building it."""
        doc_id = self.store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        return self._load(doc_id)

    def list_indexed(self) -> list[str]:
        return self.store_service.list_indexed_papers()

    # ------------------------------------------------------------------

    def _get_or_build(self, paper_id: str, strategy: RagStrategy, strategy_version: str, force: bool = False) -> RagIndex:
        doc_id = self.store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        signature = self.store_service.signature(paper_id)

        existing = self._load(doc_id)
        if existing is not None and existing.file_signature == signature and not force:
            return existing

        source_path = self.store_service.get_source_path_for_paper(paper_id)
        format = self.store_service.file_format(paper_id)
        raw_sections = self._reader.extract_structure(source_path, format)
        index = self._strategy(strategy, strategy_version).build_index(raw_sections, paper_id, doc_id, signature)
        self._save(index)
        return index

    def _strategy(self, strategy: RagStrategy, strategy_version: str) -> RetrievalStrategy:
        return RetrievalStrategy.create(strategy, strategy_version, embedder=self._embedder)

    def _load(self, doc_id: str) -> RagIndex | None:
        return self.store_service.get_rag_index(doc_id)

    def _save(self, index: RagIndex) -> None:
        self.store_service.save_rag_index(index)