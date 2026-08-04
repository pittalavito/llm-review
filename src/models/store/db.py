"""SQLModel table definitions.

Analytical facts live in typed, constrained, indexed columns (queryable via
SQL); the verbatim LLM traces live once in ``agent_trace`` — the single source
of truth for payloads: the run-level responses are DERIVED from it at read
time, never stored twice. Enum-like columns are plain strings with NO db-level
CHECK on the allowed values: the vocabulary is enforced by the Pydantic
StrEnums only, so adding an enum member never requires touching an existing
database. Numeric ranges keep their CHECKs.
"""
from sqlalchemy import JSON, CheckConstraint, Column, ForeignKey, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.domain import ranges


class GraphReviewTable(SQLModel, table=True):
    """One row per review-graph execution: the indexed analytical facts plus
    the run's ``graph_config`` (verbatim JSON)."""

    __tablename__ = "graph_review"  # type: ignore
    __table_args__ = (
        CheckConstraint("total_rounds >= 0", name="ck_graph_review_total_rounds"),
        CheckConstraint("max_rounds IS NULL OR max_rounds >= 1", name="ck_graph_review_max_rounds"),
        CheckConstraint(ranges.sql_check_between("meta_overall_score", ranges.SCORE), name="ck_graph_review_meta_overall_score"),
    )

    run_id: str = Field(primary_key=True)
    timestamp: str = Field(index=True)
    paper_id: str = Field(index=True)
    description: str | None = None
    decision: str | None = Field(default=None, index=True)
    total_rounds: int
    max_rounds: int | None = None
    meta_overall_score: int | None = None
    graph_config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class GraphReviewAgentTable(SQLModel, table=True):
    """One row per agent invocation (N per run): the full identity
    (role/index/round), extracted analytics, and the response payload + metadata."""

    __tablename__ = "graph_review_agent"  # type: ignore
    __table_args__ = (
        CheckConstraint("agent_index IS NULL OR agent_index >= 1", name="ck_graph_review_agent_index"),
        CheckConstraint('"round" >= 0', name="ck_graph_review_agent_round"),
        CheckConstraint(ranges.sql_check_between("rating", ranges.RATING), name="ck_graph_review_agent_rating"),
        CheckConstraint(ranges.sql_check_between("confidence", ranges.CONFIDENCE), name="ck_graph_review_agent_confidence"),
        CheckConstraint(ranges.sql_check_between("overall_score", ranges.SCORE), name="ck_graph_review_agent_overall_score"),
        Index("ix_graph_review_agent_run_agent_round", "run_id", "agent_role", "agent_index", "round"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(sa_column=Column(ForeignKey("graph_review.run_id", ondelete="CASCADE"), nullable=False))
    agent_role: str
    agent_index: int | None = None
    round: int
    model: str | None = None
    rating: int | None = None
    confidence: int | None = None
    overall_score: int | None = None
    decision: str | None = None
    #
    agent_trace_id: int | None = Field(default=None, sa_column=Column(ForeignKey("agent_trace.id", ondelete="SET NULL"), nullable=True))

    response_payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    system_prompt: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_seconds: float | None = None


class AgentTraceTable(SQLModel, table=True):
    """The verbatim trace of one agent invocation — single source of truth for
    the LLM payloads. Identity (role/index/round) lives on the referencing
    ``graph_review_agent`` row; ``run_id`` is kept here only so deleting a run
    cascades away its traces."""

    __tablename__ = "agent_trace"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(sa_column=Column(ForeignKey("graph_review.run_id", ondelete="CASCADE"), nullable=False))

    input_message: str | None = None
    system_prompt: str | None = None
    context_used: str | None = None
    response_payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None

    latency_seconds: float | None = None
    """Not populated yet — reserved for timing the agent invocation."""


class PromptVersionTable(SQLModel, table=True):
    """Registry of base system-prompt templates. Versions are immutable: a new
    text means a new row; only description and is_active may change afterwards."""

    __tablename__ = "prompt_version"  # type: ignore
    __table_args__ = (
        UniqueConstraint("agent_role", "version_label", name="uq_prompt_role_label"),
    )

    id: int | None = Field(default=None, primary_key=True)
    agent_role: str
    version_label: str
    template: str
    template_hash: str
    description: str | None = None
    created_at: str
    is_active: bool = True


class PromptInstructionTable(SQLModel, table=True):
    """Registry of composable persona instructions, keyed by (type, label).
    Like prompt versions they are immutable: a new text means a new row; only
    description and is_active may change afterwards."""

    __tablename__ = "prompt_instruction"  # type: ignore
    __table_args__ = (
        UniqueConstraint("type", "label", name="uq_prompt_instruction_type_label"),
    )

    id: int | None = Field(default=None, primary_key=True)
    type: str
    label: str
    instruction: str
    description: str | None = None
    agent_role: str | None = None
    run_id: str | None = None
    """Anchor to the graph run the instruction was derived from (e.g. a
    calibration written after comparing that run with OpenReview)."""
    created_at: str
    is_active: bool = True


class AuthorTable(SQLModel, table=True):
    """Catalog of paper authors, shared across papers (m2m via ``paper_author``).
    Deduplication is the repository's job: by ``openreview_profile_id`` when
    present, by (full_name, email) otherwise — no db-level unique key because
    homonyms without email are legitimate distinct rows."""

    __tablename__ = "author"  # type: ignore

    id: int | None = Field(default=None, primary_key=True)
    full_name: str = Field(index=True)
    email: str | None = None
    affiliation: str | None = None
    openreview_profile_id: str | None = Field(default=None, index=True)


class PaperAuthorTable(SQLModel, table=True):
    """Bridge paper <-> author, with the author's 1-based position in the
    paper's author list. Deleting a paper or an author cascades away the link."""

    __tablename__ = "paper_author"  # type: ignore
    __table_args__ = (
        UniqueConstraint("paper_id", "author_id", name="uq_paper_author"),
        CheckConstraint("position >= 1", name="ck_paper_author_position"),
    )

    id: int | None = Field(default=None, primary_key=True)
    paper_id: str = Field(sa_column=Column(ForeignKey("paper.paper_id", ondelete="CASCADE"), nullable=False, index=True))
    author_id: int = Field(sa_column=Column(ForeignKey("author.id", ondelete="CASCADE"), nullable=False, index=True))
    position: int = 1


class PaperTable(SQLModel, table=True):
    """Catalog of papers available to the pipeline. ``paper_id`` is an opaque
    generated uid ending with the file-format segment (``…_pdf`` / ``…_txt``,
    see ``domain.store.db.store.Factory.build_paper_id``); the paper file lives
    in the files store under the same id. OpenReview metadata columns are NULL
    for OTHER papers; num_graph_review is a snapshot of the paper's run count."""

    __tablename__ = "paper" # type: ignore
    __table_args__ = (
        CheckConstraint("num_graph_review >= 0", name="ck_paper_num_graph_review"),
        UniqueConstraint("paper_id", name="uq_paper_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    paper_id: str = Field(index=True)
    paper_name: str
    paper_type: str
    description: str | None = None
    conference: str | None = None
    open_review_id: str | None = None
    openreview_api_version: str | None = None
    human_decision: str | None = None
    num_graph_review: int = 0


class OpenReviewTable(SQLModel, table=True):
    """Parsed OpenReview data extracted from loaded papers. One row per
    review/meta-review/area-chair decision. Linked to paper via ``paper_id``."""

    __tablename__ = "open_review"  # type: ignore
    __table_args__ = (
        CheckConstraint("reviewer_index IS NULL OR reviewer_index >= 1", name="ck_open_review_reviewer_index"),
        CheckConstraint(ranges.sql_check_between("rating", ranges.RATING), name="ck_open_review_rating"),
        CheckConstraint(ranges.sql_check_between("confidence", ranges.CONFIDENCE), name="ck_open_review_confidence"),
        CheckConstraint(ranges.sql_check_between("overall_score", ranges.SCORE), name="ck_open_review_overall_score"),
        Index("ix_open_review_paper", "paper_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    paper_id: str = Field(sa_column=Column(ForeignKey("paper.paper_id", ondelete="CASCADE"), nullable=False, index=True))
    note_id: str
    reviewer_type: str
    reviewer_id: str | None = None
    reviewer_index: int | None = None

    rating: int | None = None
    confidence: int | None = None
    overall_score: int | None = None
    decision: str | None = None
    recommendation: str | None = None

    significance_and_novelty: str | None = None
    review_text: str | None = None
    summary: str | None = None
    justification: str | None = None

    created_at: str = Field(index=True)
    updated_at: str
