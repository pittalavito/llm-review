"""Single persistence facade for the app.

Composes every repository behind one service-layer object: the DB repositories
(runs, paper catalog, prompt-version registry) and the Redis repositories (RAG
index, OpenReview cache), all built internally from the config — nothing is
injected.

Everything comes from the per-store facades ``domain.store.db.store`` and
``domain.store.redis.store``: the repository classes plus each store's own
``Adapter`` (store record → domain model, reads) and ``Factory`` (domain model →
store record, writes). The repositories deal only in rows/records.
"""
from core.observability import observed, LogPrefix

from domain.prompt.default import DEFAULT_PROMPT_SEEDS

from domain.store.db.store import Adapter as DbAdapter, Factory as DbFactory, DbPaperRepository, DbPromptRepository, DbResultRepository
from domain.store.redis.store import Adapter as RedisAdapter, Factory as RedisFactory, RedisRagIndexRepository, RedisOpenReviewCacheRepository
from domain.store.files.store import FilePaperRepository

from models.domain.agent import AgentRole
from models.domain.comparator import HumanMetaReview, HumanReview
from models.domain.openreview import OpenReviewCache
from models.domain.paper import Paper
from models.domain.prompt import PromptVersion
from models.domain.retrieval import IndexInfo, RagFileSignature, RagIndex
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord, GraphReviewSummary

class StoreService:

    @observed(LogPrefix.STORE_SERVICE)
    def __init__(self):
        self._results_repository = DbResultRepository()
        self._papers_repository = DbPaperRepository()
        self._prompts_repository = DbPromptRepository()
        self._rag_index_repository = RedisRagIndexRepository()
        self._cache_repository = RedisOpenReviewCacheRepository()
        self._papers_files_repository = FilePaperRepository()

        self.seed_prompts(DEFAULT_PROMPT_SEEDS)
    
    def save_paper(self, paper: Paper, data: bytes) -> Paper | None:
        """Create the catalog row and store the file under its paper_id.
        None when a paper with the same id already exists."""
        db_row = self.create_paper(paper)
        if db_row is None:
            return None
        self.save_paper_file(db_row.paper_id, data)
        return db_row
    
    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    @staticmethod
    def build_run_id(paper_id: str) -> str:
        return DbResultRepository.build_run_id(paper_id)

    def save_run(self, record: GraphReviewRecord) -> str:
        run_row = DbFactory.to_run_row(record)
        payload_row = DbFactory.to_run_payload_row(record)
        agent_pairs = DbFactory.to_agent_pairs(record.run_id, record.agent_runs)
        return self._results_repository.save_rows(run_row, payload_row, agent_pairs)

    def list_runs(self) -> list[GraphReviewSummary]:
        return DbAdapter.to_run_summaries(self._results_repository.list_summaries())

    def get_run(self, run_id: str) -> GraphReviewRecord | None:
        rows = self._results_repository.get_rows(run_id)
        return DbAdapter.to_run_record(*rows) if rows is not None else None

    def get_agent_runs(self, run_id: str, agent_role: AgentRole | None = None, agent_index: int | None = None, round_index: int | None = None) -> list[AgentResponseRecord] | None:
        role = str(agent_role) if agent_role is not None else None
        pairs = self._results_repository.get_agent_run_rows(run_id, role, agent_index, round_index)
        return DbAdapter.to_agent_runs(pairs) if pairs is not None else None

    def get_run_ids_for_paper(self, paper_id: str) -> list[str]:
        return self._results_repository.list_run_ids_for_paper(paper_id)

    # ------------------------------------------------------------------
    # Paper db
    # ------------------------------------------------------------------

    def list_papers_catalog(self) -> list[Paper]:
        return DbAdapter.to_papers(self._papers_repository.list())

    def list_paper_ids(self) -> list[str]:
        return self._papers_repository.list_ids()

    def list_openreview_papers(self) -> list[Paper]:
        return DbAdapter.to_papers(self._papers_repository.list_openreview())

    def get_paper(self, paper_id: str) -> Paper | None:
        row = self._papers_repository.get_by_id(paper_id)
        return DbAdapter.to_paper(row) if row is not None else None

    def create_paper(self, paper: Paper) -> Paper | None:
        to_row = DbFactory.to_paper_row(paper)
        row = self._papers_repository.create(to_row)
        return DbAdapter.to_paper(row) if row is not None else None
    
    # ------------------------------------------------------------------
    # Prompt version registry
    # ------------------------------------------------------------------

    def list_prompts(self, agent_role: str | None = None, include_inactive: bool = False) -> list[PromptVersion]:
        return DbAdapter.to_prompts(self._prompts_repository.list(agent_role, include_inactive))

    def get_prompt(self, version_id: int) -> PromptVersion | None:
        row = self._prompts_repository.get(version_id)
        return DbAdapter.to_prompt(row) if row is not None else None

    def get_promt_by_role_label(self, agent_role: str, version_label: str, only_active: bool = True) -> PromptVersion | None:
        row = self._prompts_repository.get_by_role_label(agent_role, version_label, only_active)
        return DbAdapter.to_prompt(row) if row is not None else None

    def create_prompt(self, agent_role: str, version_label: str, template: str, description: str | None = None) -> PromptVersion | None:
        row = self._prompts_repository.create(agent_role, version_label, template, description)
        return DbAdapter.to_prompt(row) if row is not None else None

    def update_prompt_meta(self, version_id: int, description: str | None = None, is_active: bool | None = None) -> PromptVersion | None:
        row = self._prompts_repository.update_meta(version_id, description, is_active)
        return DbAdapter.to_prompt(row) if row is not None else None

    def seed_prompts(self, seeds: list[tuple[str, str, str, str]]) -> int:
        return self._prompts_repository.seed_defaults(seeds)

    # ------------------------------------------------------------------
    # RAG index (Redis) — the record is already the domain shape
    # ------------------------------------------------------------------

    @staticmethod
    def compute_doc_id(paper_id: str, strategy: str, strategy_version: str) -> str:
        return RedisRagIndexRepository.compute_doc_id(paper_id, strategy, strategy_version)

    def get_rag_index(self, doc_id: str) -> RagIndex | None:
        record = self._rag_index_repository.load(doc_id)
        return RedisAdapter.to_rag_index(record) if record is not None else None

    def save_rag_index(self, index: RagIndex) -> None:
        self._rag_index_repository.save(RedisFactory.to_rag_index_record(index))

    def list_indexed_papers(self) -> list[str]:
        return self._rag_index_repository.list_indexed()

    def get_index_info(self, doc_id: str) -> IndexInfo | None:
        index = self.get_rag_index(doc_id)
        return RedisAdapter.to_index_info(index) if index is not None else None

    def get_full_paper_text(self, doc_id: str) -> str | None:
        index = self.get_rag_index(doc_id)
        return RedisAdapter.to_full_paper_text(index) if index is not None else None

    # ------------------------------------------------------------------
    # OpenReview cache (Redis) — the record is already the domain shape
    # ------------------------------------------------------------------

    def get_open_review_cache(self, key: str) -> OpenReviewCache | None:
        record = self._cache_repository.load(key)
        return RedisAdapter.to_open_review_cache(record) if record is not None else None

    def save_open_review_cache(self, key: str, cache: OpenReviewCache) -> None:
        self._cache_repository.save(key, RedisFactory.to_open_review_cache_record(cache))

    def get_human_reviews(self, key: str) -> list[HumanReview]:
        cache = self.get_open_review_cache(key)
        return RedisAdapter.to_human_reviews(cache) if cache is not None else []

    def get_human_meta_review(self, key: str) -> HumanMetaReview | None:
        cache = self.get_open_review_cache(key)
        return RedisAdapter.to_human_meta_review(cache) if cache is not None else None

    def get_open_review_decision(self, key: str) -> str | None:
        cache = self.get_open_review_cache(key)
        return RedisAdapter.to_open_review_decision(cache) if cache is not None else None

    # ------------------------------------------------------------------
    # Paper files (local filesystem) — the record is already the domain shape
    # ------------------------------------------------------------------
    
    def get_source_path_for_paper(self, paper_id: str) -> str | None:
        return self._papers_files_repository.resolve(paper_id)
    
    def signature(self, paper_id: str) -> RagFileSignature:
        return self._papers_files_repository.signature(paper_id)

    def file_format(self, paper_id: str) -> str:
        return self._papers_files_repository.file_format(paper_id)
    
    def save_paper_file(self, paper_id: str, data: bytes) -> None:
        self._papers_files_repository.save(paper_id, data)
