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

    __tablename__ = "graph_review"
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
    (role/index/round) and the extracted analytics. ``id`` preserves the
    original order; the verbatim trace lives in ``agent_trace`` (1:1 via
    ``agent_trace_id``)."""

    __tablename__ = "graph_review_agent"
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
    rating: int | None = None
    confidence: int | None = None
    overall_score: int | None = None
    decision: str | None = None
    agent_trace_id: int | None = Field(default=None, sa_column=Column(ForeignKey("agent_trace.id", ondelete="SET NULL"), nullable=True))


class AgentTraceTable(SQLModel, table=True):
    """The verbatim trace of one agent invocation — single source of truth for
    the LLM payloads. Identity (role/index/round) lives on the referencing
    ``graph_review_agent`` row; ``run_id`` is kept here only so deleting a run
    cascades away its traces."""

    __tablename__ = "agent_trace"

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

    __tablename__ = "prompt_version"
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


class PaperTable(SQLModel, table=True):
    """Catalog of papers available to the pipeline. ``paper_id`` is the
    business key in the form ``<paper-type>_<name>_<extension>`` (see
    ``domain.store.db.store.Factory.build_paper_id``); the paper file lives in
    the files store under the same id. OpenReview metadata columns are NULL for
    OTHER papers; num_graph_review is a snapshot of the paper's run count."""

    __tablename__ = "paper"
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
