from langchain_core.tools import BaseTool, tool

from config import get_global_config
from core.observability import observed, LogPrefix
from domain.retrieval.base import ChatSummarizer, Embedder, MockEmbedder, PaperFileReader, RetrievalStrategy, Summarizer
from domain.store.redis.store import Adapter as RedisAdapter
from models.domain.agent import CreateAgentRequest, ContextMode
from models.domain.chat import ChatModelName
from models.domain.retrieval import IndexInfo, RagIndex, RagStrategy
from service.chat_service import ChatService
from service.store_service import StoreService

MOCK_EMBEDD: Embedder = MockEmbedder()

_FULL_CONTEXT_VERSION = "v1"

# Current version per strategy: bump one entry when its indexing logic changes
# (old keys are simply orphaned in Redis and rebuilt lazily under the new one).
# v2 (bm25/embedding): sentence-aware Chunker + punctuation-insensitive BM25 tokens.
_STRATEGY_VERSIONS = {
    RagStrategy.FULL_CONTEXT: _FULL_CONTEXT_VERSION,
    RagStrategy.BM25: "v2",
    RagStrategy.EMBEDDING: "v2",
}

class RetrievalService:

    def __init__(self, store_service: StoreService, chat_service: ChatService):
        self._store_service = store_service
        self._chat_service = chat_service
        self._reader = PaperFileReader()
        self._embedder = MOCK_EMBEDD
        self._summarizer: Summarizer | None = None

    def get_agent_context(self, request: CreateAgentRequest) -> str | None:
        """Context text for one agent, from its AgentRequestContext: nothing for
        NONE, the whole paper for FULL_CONTEXT, the cached LLM summary for
        SUMMARY, a query-driven retrieval otherwise."""
        context = request.context
        if context is None or context.context_mode == ContextMode.NONE:
            return None
        if context.context_mode == ContextMode.FULL_CONTEXT:
            return self.retrieve_context(paper_id=request.paper_id, query="", strategy=RagStrategy.FULL_CONTEXT, strategy_version=self._version(RagStrategy.FULL_CONTEXT))
        if context.context_mode == ContextMode.SUMMARY:
            return self.retrieve_context(paper_id=request.paper_id, query="", strategy=RagStrategy.SUMMARY, strategy_version=self._version(RagStrategy.SUMMARY))
        query = context.retrieval_context_query or request.retrieval_context_query
        if query is None:
            raise ValueError("retrieval_context_query must be provided for BM25 or EMBEDDING context modes.")
        strategy = RagStrategy(context.context_mode)
        return self.retrieve_context(paper_id=request.paper_id, query=query, strategy=strategy, strategy_version=self._version(strategy))

    def retrieve_context(self, paper_id: str, query: str, strategy: RagStrategy, strategy_version: str, top_k: int | None = None) -> str:
        """Context text for ``query`` under ``strategy`` — indexing the paper first
        if there is no fresh index for this (paper, strategy, version)."""
        index = self._get_or_build(paper_id, strategy, strategy_version)
        return self._strategy(strategy, strategy_version, top_k=top_k).build_context(index, query)

    def build_retrieval_tool(self, paper_id: str, top_k: int) -> BaseTool:
        """A LangChain tool closed over ``(paper_id, top_k)`` that an agent can
        call during its invocation: BM25 search over this paper's index."""
        retrieve = self.retrieve_context
        bm25_version = self._version(RagStrategy.BM25)

        @tool("search_paper")
        def search_paper(query: str) -> str:
            """Search the paper under review for passages relevant to the query. Returns the most relevant excerpts, each under its section heading."""
            passages = retrieve(paper_id, query, RagStrategy.BM25, bm25_version, top_k=top_k)
            return passages or "No relevant passages found."

        return search_paper

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
        """All the (strategy, version) indexes for this paper, with their
        lightweight metadata. Full-context goes first so the chunk strategies
        recycle its parsed sections. SUMMARY is deliberately absent: it costs an
        LLM call and is built lazily on first use instead."""
        index_list: list[IndexInfo] = []
        for strategy in (RagStrategy.FULL_CONTEXT, RagStrategy.BM25, RagStrategy.EMBEDDING):
            index_list.append(self.index_paper(paper_id, strategy, self._version(strategy)))
        return index_list
    
    # ------------------------------------------------------------------

    def _get_or_build(self, paper_id: str, strategy: RagStrategy, strategy_version: str, force: bool = False) -> RagIndex:
        doc_id = self._store_service.compute_doc_id(paper_id, str(strategy), strategy_version)
        signature = self._store_service.signature(paper_id)
        existing = self._load(doc_id)
        if existing is not None and existing.file_signature == signature and not force:
            return existing
        
        raw_sections = None if force else self._sections_from_full_context(paper_id, signature)
        if raw_sections is None:
            source_path = self._store_service.get_source_path_for_paper(paper_id)
            format = self._store_service.file_format(paper_id)
            raw_sections = self._reader.extract_structure(source_path, format)
        index = self._strategy(strategy, strategy_version).build_index(raw_sections, paper_id, doc_id, signature)
        self._save(index)
        return index

    def _sections_from_full_context(self, paper_id: str, signature) -> list[tuple[str, str]] | None:
        """Recycle the parsed sections of a fresh full-context index (its own
        version, regardless of the caller's) to skip the expensive file parse."""
        full_context = self.get_index(paper_id, RagStrategy.FULL_CONTEXT, _FULL_CONTEXT_VERSION)
        if full_context is None or full_context.file_signature != signature or not full_context.sections:
            return None
        return [(section.name, section.text) for section in full_context.sections]

    def _strategy(self, strategy: RagStrategy, strategy_version: str, top_k: int | None = None) -> RetrievalStrategy:
        summarizer = self._get_summarizer() if strategy is RagStrategy.SUMMARY else None
        if top_k is None:
            return RetrievalStrategy.create(strategy, strategy_version, embedder=self._embedder, summarizer=summarizer)
        return RetrievalStrategy.create(strategy, strategy_version, embedder=self._embedder, summarizer=summarizer, top_k=top_k)

    def _version(self, strategy: RagStrategy) -> str:
        """Current index version for ``strategy``. The summary version is keyed
        on the summarizer model: changing the model in config invalidates the
        cached summaries via a new doc_id."""
        if strategy is RagStrategy.SUMMARY:
            return f"v1-{get_global_config().summarizer_model}"
        return _STRATEGY_VERSIONS[strategy]

    def _get_summarizer(self) -> Summarizer:
        if self._summarizer is None:
            config = get_global_config()
            chat = self._chat_service.build_chat(model=ChatModelName(config.summarizer_model), temperature=config.summarizer_temperature)
            self._summarizer = ChatSummarizer(chat, max_input_chars=config.summarizer_max_input_chars)
        return self._summarizer

    def _load(self, doc_id: str) -> RagIndex | None:
        return self._store_service.get_rag_index(doc_id)

    def _save(self, index: RagIndex) -> None:
        self._store_service.save_rag_index(index)