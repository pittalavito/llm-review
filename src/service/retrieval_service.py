from core.observability import observed, LogPrefix
from domain.retrieval.base import Embedder, MockEmbedder, PaperFileReader, RetrievalStrategy
from domain.store.redis.store import Adapter as RedisAdapter
from domain.models.agent import CreateAgentRequest, ContextMode
from domain.models.retrieval import IndexInfo, RagIndex, RagStrategy
from service.store_service import StoreService

MOCK_EMBEDD: Embedder = MockEmbedder()

class RetrievalService:

    def __init__(self, store_service: StoreService):
        self._store_service = store_service
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

    @observed(LogPrefix.RETRIEVAL_SERVICE)
    def index_paper(self, paper_id: str, strategy: RagStrategy, strategy_version: str, force: bool = False) -> IndexInfo:
        """Ensure the paper is indexed under (strategy, version); rebuild when the
        file changed or ``force``. Returns the lightweight index metadata."""
        index = self._get_or_build(paper_id, strategy, strategy_version, force=force)
        return RedisAdapter.to_index_info(index)

    def get_index(self, paper_id: str, strategy: RagStrategy, strategy_version: str) -> RagIndex | None:
        """The stored index for (paper, strategy, version), without building it."""
        doc_id = self._store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        return self._load(doc_id)

    def get_index_info(self, paper_id: str, strategy: RagStrategy, strategy_version: str) -> IndexInfo | None:
        """Lightweight metadata of the stored index (None when not indexed yet).
        Used by the FE to poll a background indexing for completion."""
        doc_id = self._store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        return self._store_service.get_index_info(doc_id)

    def list_indexed(self) -> list[str]:
        return self._store_service.list_indexed_papers()

    def multi_strategy_indexed(self, paper_id: str) -> list[IndexInfo]:
        """All the (strategy, version) indexes for this paper, with their lightweight metadata."""
        index_list: list[IndexInfo] = []
        index_list.append(self.index_paper(paper_id, RagStrategy.FULL_CONTEXT, "v1"))
        index_list.append(self.index_paper(paper_id, RagStrategy.BM25, "v1"))
        index_list.append(self.index_paper(paper_id, RagStrategy.EMBEDDING, "v1"))
        return index_list
    
    # ------------------------------------------------------------------

    def _get_or_build(self, paper_id: str, strategy: RagStrategy, strategy_version: str, force: bool = False) -> RagIndex:
        doc_id = self._store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        signature = self._store_service.signature(paper_id)
        existing = self._load(doc_id)
        if existing is not None and existing.file_signature == signature and not force:
            return existing
        
        raw_sections = None if force else self._sections_from_full_context(paper_id, strategy_version, signature)
        if raw_sections is None:
            source_path = self._store_service.get_source_path_for_paper(paper_id)
            format = self._store_service.file_format(paper_id)
            raw_sections = self._reader.extract_structure(source_path, format)
        index = self._strategy(strategy, strategy_version).build_index(raw_sections, paper_id, doc_id, signature)
        self._save(index)
        return index

    def _sections_from_full_context(self, paper_id: str, strategy_version: str, signature) -> list[tuple[str, str]] | None:
        full_context = self.get_index(paper_id, RagStrategy.FULL_CONTEXT, strategy_version)
        if full_context is None or full_context.file_signature != signature or not full_context.sections:
            return None
        return [(section.name, section.text) for section in full_context.sections]

    def _strategy(self, strategy: RagStrategy, strategy_version: str) -> RetrievalStrategy:
        return RetrievalStrategy.create(strategy, strategy_version, embedder=self._embedder)

    def _load(self, doc_id: str) -> RagIndex | None:
        return self._store_service.get_rag_index(doc_id)

    def _save(self, index: RagIndex) -> None:
        self._store_service.save_rag_index(index)