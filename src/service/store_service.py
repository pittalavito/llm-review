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
from domain.prompt.instruction_default import DEFAULT_INSTRUCTION_SEEDS

from domain.store.db.store import Adapter as DbAdapter, Factory as DbFactory, DbAuthorRepository, DbInstructionRepository, DbPaperRepository, DbPromptRepository, DbRunRepository
from domain.store.db.open_review_repository import DbOpenReviewRepository
from domain.store.db.open_review_adapter import OpenReviewAdapter
from domain.store.redis.store import Adapter as RedisAdapter, Factory as RedisFactory, RedisRagIndexRepository
from domain.store.files.store import FilePaperRepository

from models.domain.agent import AgentRole
from models.domain.comparator import HumanMetaReview, HumanReview
from models.domain.openreview import OpenReviewNotes
from models.domain.paper import Author, Paper
from models.store.db import OpenReviewTable
from models.domain.prompt import InstructionType, PromptInstruction, PromptVersion
from models.domain.retrieval import IndexInfo, RagFileSignature, RagIndex
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord, GraphReviewSummary

class StoreService:

    @observed(LogPrefix.STORE_SERVICE)
    def __init__(self):
        self._runs_repository = DbRunRepository()
        self._papers_repository = DbPaperRepository()
        self._authors_repository = DbAuthorRepository()
        self._prompts_repository = DbPromptRepository()
        self._instructions_repository = DbInstructionRepository()
        self._open_review_repository = DbOpenReviewRepository()
        self._rag_index_repository = RedisRagIndexRepository()
        self._papers_files_repository = FilePaperRepository()

        self.seed_prompts(DEFAULT_PROMPT_SEEDS)
        self.seed_instructions(DEFAULT_INSTRUCTION_SEEDS)
    
    def save_paper(self, paper: Paper, data: bytes, file_format: str, authors: list[Author] | None = None) -> Paper | None:
        """Create the catalog row (paper_id generated as uid + ``file_format``
        suffix), store the file under it and link the authors (deduplicated,
        in list order). None when a paper with the same id already exists."""
        db_row = self.create_paper(paper, file_format)
        if db_row is None:
            return None
        self.save_paper_file(db_row.paper_id, data)
        if authors:
            self.save_paper_authors(db_row.paper_id, authors)
        return db_row
    
    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    @staticmethod
    def build_run_id(paper_id: str) -> str:
        return DbRunRepository.build_run_id(paper_id)

    def save_run(self, record: GraphReviewRecord) -> str:
        return self._runs_repository.save_rows(*DbFactory.to_run_rows(record))

    def list_runs(self) -> list[GraphReviewSummary]:
        return DbAdapter.to_run_summaries(self._runs_repository.list_summaries())

    def get_run(self, run_id: str) -> GraphReviewRecord | None:
        rows = self._runs_repository.get_rows(run_id)
        return DbAdapter.to_run_record(*rows) if rows is not None else None

    def get_run_ids_for_paper(self, paper_id: str) -> list[str]:
        return self._runs_repository.list_run_ids_for_paper(paper_id)

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

    def create_paper(self, paper: Paper, file_format: str) -> Paper | None:
        to_row = DbFactory.to_paper_row(paper, file_format)
        row = self._papers_repository.create(to_row)
        return DbAdapter.to_paper(row) if row is not None else None

    # ------------------------------------------------------------------
    # Authors db
    # ------------------------------------------------------------------

    def save_paper_authors(self, paper_id: str, authors: list[Author]) -> list[Author]:
        """Link the authors to the paper in list order (1-based position),
        creating the author rows that do not exist yet (dedup by openreview
        profile id, else by name+email). Returns the linked authors."""
        linked: list[Author] = []
        for index, author in enumerate(authors, start=1):
            row = self._authors_repository.get_or_create(DbFactory.to_author_row(author))
            position = author.position or index
            self._authors_repository.link_to_paper(paper_id, row.id, position)
            linked.append(DbAdapter.to_author(row, position))
        return linked

    def get_paper_authors(self, paper_id: str) -> list[Author]:
        """The paper's authors with their positions, ordered by position."""
        return DbAdapter.to_authors(self._authors_repository.list_for_paper(paper_id))

    def get_papers_for_author(self, author_id: int) -> list[str]:
        """The paper_ids the author is linked to."""
        return self._authors_repository.list_papers_for_author(author_id)
    
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
    # Prompt instruction registry (persona axes)
    # ------------------------------------------------------------------
    def get_instructions_by_labels(self, labels: list[str]) -> list[PromptInstruction]:
        rows = self._instructions_repository.list_by_labels(labels)
        return DbAdapter.to_instructions(rows)

    def list_instructions(self, type: InstructionType | None = None, include_inactive: bool = False) -> list[PromptInstruction]:
        type_value = str(type) if type is not None else None
        rows = self._instructions_repository.list(type_value, include_inactive)
        return DbAdapter.to_instructions(rows)  

    def create_instruction(self, type: InstructionType, label: str, instruction: str, description: str | None = None, agent_role: str | None = None) -> PromptInstruction | None:
        row = self._instructions_repository.create(str(type), label, instruction, description, agent_role)
        return DbAdapter.to_instruction(row) if row is not None else None

    def update_instruction_meta(self, instruction_id: int, description: str | None = None, is_active: bool | None = None) -> PromptInstruction | None:
        row = self._instructions_repository.update_meta(instruction_id, description, is_active)
        return DbAdapter.to_instruction(row) if row is not None else None

    def seed_instructions(self, seeds: list[tuple[InstructionType, str, str, str, str]]) -> int:
        return self._instructions_repository.seed_defaults(seeds)

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
    # OpenReview data (SQL)
    # ------------------------------------------------------------------

    def save_open_review_data(self, paper_id: str, notes: OpenReviewNotes) -> None:
        """Parse OpenReview cache and save structured review data to DB."""
        records = OpenReviewAdapter.from_notes(notes, paper_id)
        if records:
            self._open_review_repository.create_batch(records)

    def get_open_review_data(self, paper_id: str) -> list:
        """Get all parsed review records for a paper."""
        return self._open_review_repository.list_by_paper(paper_id)

    def get_human_reviews(self, paper_id: str) -> list[HumanReview]:
        """Get HumanReview objects from SQL for a paper."""
        rows = self._open_review_repository.list_by_paper(paper_id)
        return OpenReviewAdapter.to_human_reviews_from_rows(rows)

    def get_human_meta_review(self, paper_id: str) -> HumanMetaReview | None:
        """Get HumanMetaReview from SQL for a paper."""
        rows = self._open_review_repository.list_by_paper(paper_id)
        return OpenReviewAdapter.to_human_meta_reviews_from_rows(rows)

    # ------------------------------------------------------------------
    # Paper files (local filesystem) — the record is already the domain shape
    # ------------------------------------------------------------------
    
    def get_source_path_for_paper(self, paper_id: str):
        return self._papers_files_repository.resolve(paper_id)
    
    def signature(self, paper_id: str) -> RagFileSignature:
        return self._papers_files_repository.signature(paper_id)

    def file_format(self, paper_id: str) -> str:
        return self._papers_files_repository.file_format(paper_id)
    
    def save_paper_file(self, paper_id: str, data: bytes) -> None:
        self._papers_files_repository.save(paper_id, data)
