"""SQLModel table definitions.

Analytical facts live in typed, constrained, indexed columns (queryable via
SQL); the verbatim LLM payloads live as JSON in dedicated payload tables, one
row per parent (1:1, linked by foreign key). Enum-like columns are plain
strings guarded by CHECK constraints whose value tuples derive from the project
StrEnums via ``ranges.sql_in`` (one source of truth).
"""
from sqlalchemy import JSON, CheckConstraint, Column, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from domain.models import ranges
from domain.models.agent import AgentName, AgentRole
from domain.models.paper import PaperType

_AGENT_NAMES_SQL = ranges.sql_in(AgentName)
_AGENT_ROLES_SQL = ranges.sql_in(AgentRole)
_PAPER_TYPES_SQL = ranges.sql_in(PaperType)


class ReviewRunTable(SQLModel, table=True):
    """One row per review-graph execution: the indexed analytical facts.
    The verbatim payloads live in ``review_run_payload`` (1:1)."""

    __tablename__ = "review_run"
    __table_args__ = (
        CheckConstraint("total_rounds >= 0", name="ck_review_run_total_rounds"),
        CheckConstraint("max_rounds IS NULL OR max_rounds >= 1", name="ck_review_run_max_rounds"),
        CheckConstraint(ranges.sql_check_between("meta_overall_score", ranges.SCORE), name="ck_review_run_meta_overall_score"),
    )

    run_id: str = Field(primary_key=True)
    timestamp: str = Field(index=True)
    paper_path: str = Field(index=True)
    run_description: str | None = None
    decision: str | None = Field(default=None, index=True)
    total_rounds: int
    max_rounds: int | None = None
    meta_overall_score: int | None = None


class ReviewRunPayloadTable(SQLModel, table=True):
    """Verbatim JSON payloads for one review run (1:1 with review_run)."""

    __tablename__ = "review_run_payload"

    run_id: str = Field(
        sa_column=Column(String, ForeignKey("review_run.run_id", ondelete="CASCADE"), primary_key=True)
    )
    reviews: list[str] | None = Field(default=None, sa_column=Column(JSON))
    meta_review: dict | None = Field(default=None, sa_column=Column(JSON))
    area_chair_response: dict | None = Field(default=None, sa_column=Column(JSON))
    author_response: dict | None = Field(default=None, sa_column=Column(JSON))
    retrieval_metadata: dict | None = Field(default=None, sa_column=Column(JSON))
    graph_config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))


class ReviewAgentRunTable(SQLModel, table=True):
    """One row per agent invocation (N per run): the extracted analytics.
    ``id`` preserves the original order; the verbatim payloads live in
    ``review_agent_run_payload`` (1:1)."""

    __tablename__ = "review_agent_run"
    __table_args__ = (
        CheckConstraint(f"agent IN {_AGENT_NAMES_SQL}", name="ck_review_agent_run_agent"),
        CheckConstraint('"round" >= 0', name="ck_review_agent_run_round"),
        CheckConstraint(ranges.sql_check_between("rating", ranges.RATING), name="ck_review_agent_run_rating"),
        CheckConstraint(ranges.sql_check_between("confidence", ranges.CONFIDENCE), name="ck_review_agent_run_confidence"),
        CheckConstraint(ranges.sql_check_between("overall_score", ranges.SCORE), name="ck_review_agent_run_overall_score"),
        Index("ix_review_agent_run_run_agent_round", "run_id", "agent", "round"),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(sa_column=Column(ForeignKey("review_run.run_id", ondelete="CASCADE"), nullable=False))
    agent: str
    round: int
    input_message: str
    context_used: str | None = None
    rating: int | None = None
    confidence: int | None = None
    overall_score: int | None = None
    decision: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ReviewAgentRunPayloadTable(SQLModel, table=True):
    """Verbatim JSON payloads for one agent invocation (1:1 with review_agent_run)."""

    __tablename__ = "review_agent_run_payload"

    agent_run_id: int = Field(
        sa_column=Column(Integer, ForeignKey("review_agent_run.id", ondelete="CASCADE"), primary_key=True)
    )
    response_payload: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    prompt_trace: dict | None = Field(default=None, sa_column=Column(JSON))
    runtime_trace: dict | None = Field(default=None, sa_column=Column(JSON))


class PromptVersionTable(SQLModel, table=True):
    """Registry of base system-prompt templates. Versions are immutable: a new
    text means a new row; only description and is_active may change afterwards."""

    __tablename__ = "prompt_version"
    __table_args__ = (
        CheckConstraint(f"agent_role IN {_AGENT_ROLES_SQL}", name="ck_prompt_version_role"),
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
    """Catalog of papers available to the pipeline. OpenReview metadata columns
    are NULL for OTHER papers; num_review is a snapshot of the paper's run count."""

    __tablename__ = "paper"
    __table_args__ = (
        CheckConstraint(f"paper_type IN {_PAPER_TYPES_SQL}", name="ck_paper_type"),
        CheckConstraint("num_review >= 0", name="ck_paper_num_review"),
        UniqueConstraint("paper_path", name="uq_paper_path"),
    )

    id: int | None = Field(default=None, primary_key=True)
    paper_path: str = Field(index=True)
    paper_name: str
    paper_type: str
    open_review_id: str | None = None
    conference: str | None = None
    openreview_api_version: str | None = None
    decision: str | None = None
    num_review: int = 0


class ReviewAgentConfigTable(SQLModel, table=True):
    """Per-agent LLM configuration for a run, normalized from the graph config."""

    __tablename__ = "review_agent_config"
    __table_args__ = (
        CheckConstraint(f"agent_name IN {_AGENT_NAMES_SQL}", name="ck_review_agent_config_agent_name"),
        CheckConstraint("temperature BETWEEN 0 AND 2", name="ck_review_agent_config_temperature"),
        UniqueConstraint("run_id", "agent_name", name="uq_review_agent_config_run_agent"),
    )

    model_config = {"protected_namespaces": ()}
    id: int | None = Field(default=None, primary_key=True)
    run_id: str = Field(sa_column=Column(ForeignKey("review_run.run_id", ondelete="CASCADE"), nullable=False))
    agent_name: str
    model: str = Field(index=True)
    temperature: float
    prompt_version: str | None = None
    prompt_version_id: int | None = Field(default=None, sa_column=Column(ForeignKey("prompt_version.id"), nullable=True))
    persona_commitment: str | None = None
    persona_intention: str | None = None
    persona_knowledgeability: str | None = None
    persona_focus: str | None = None
    area_chair_style: str | None = None
