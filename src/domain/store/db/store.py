"""DB store facade: one import point for the DB persistence layer.

Re-exports the DB repositories and holds the two DB translation seams as
static-method classes: ``Adapter`` (rows -> domain models, reads) and ``Factory``
(domain models -> rows, writes). The run-level responses (reviews, meta review,
area chair, author) are never persisted twice: ``Adapter.to_run_record``
DERIVES them from the agent traces, the single source of truth.
"""
from pathlib import PurePosixPath

from domain.store.db.author_repository import DbAuthorRepository
from domain.store.db.instruction_repository import DbInstructionRepository
from domain.store.db.paper_repository import DbPaperRepository
from domain.store.db.prompt_repository import DbPromptRepository
from domain.store.db.run_repository import AgentRecordPair, DbRunRepository

from models.domain.agent import AgentRole
from models.domain.paper import Author, Paper, PaperType
from models.domain.prompt import PromptInstruction, PromptVersion
from models.domain.run_record import AgentResponseRecord, GraphReviewRecord, GraphReviewSummary

from models.store.db import (
    AgentTraceTable,
    AuthorTable,
    GraphReviewAgentTable,
    GraphReviewTable,
    PaperTable,
    PromptInstructionTable,
    PromptVersionTable,
)


__all__ = ["DbAuthorRepository", "DbInstructionRepository", "DbPaperRepository", "DbPromptRepository", "DbRunRepository", "Adapter", "Factory"]


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_paper(row: PaperTable) -> Paper:
        """``PaperTable`` row -> ``Paper`` (field-for-field; ``paper_type`` str -> ``PaperType``)."""
        return Paper(
            id=row.id,
            paper_id=row.paper_id,
            paper_name=row.paper_name,
            paper_type=PaperType(row.paper_type),
            description=row.description,
            open_review_id=row.open_review_id,
            conference=row.conference,
            openreview_api_version=row.openreview_api_version,
            human_decision=row.human_decision,
            num_graph_review=row.num_graph_review,
        )

    @staticmethod
    def to_author(row: AuthorTable, position: int | None = None) -> Author:
        """``AuthorTable`` row -> ``Author``; ``position`` comes from the
        paper_author link when reading a specific paper's author list."""
        return Author(
            id=row.id,
            full_name=row.full_name,
            email=row.email,
            affiliation=row.affiliation,
            openreview_profile_id=row.openreview_profile_id,
            position=position,
        )

    @staticmethod
    def to_prompt(row: PromptVersionTable) -> PromptVersion:
        """``PromptVersionTable`` row -> ``PromptVersion`` (field-for-field)."""
        return PromptVersion.model_validate(row.model_dump())

    @staticmethod
    def to_instruction(row: PromptInstructionTable) -> PromptInstruction:
        """``PromptInstructionTable`` row -> ``PromptInstruction`` (field-for-field)."""
        return PromptInstruction.model_validate(row.model_dump())

    @staticmethod
    def to_run_summary(row: GraphReviewTable) -> GraphReviewSummary:
        """``graph_review`` row -> lightweight ``GraphReviewSummary`` (facts only,
        analytics included)."""
        return GraphReviewSummary(
            run_id=row.run_id,
            timestamp=row.timestamp,
            paper_id=row.paper_id,
            description=row.description,
            decision=row.decision,
            total_rounds=row.total_rounds,
            max_rounds=row.max_rounds,
            meta_overall_score=row.meta_overall_score,
        )

    @staticmethod
    def to_run_record(
        run_row: GraphReviewTable,
        agent_rows: list[GraphReviewAgentTable],
        traces: dict[int, AgentTraceTable | None],
    ) -> GraphReviewRecord:
        """Reassemble a full ``GraphReviewRecord`` from the run row and its
        agent rows + traces. The run-level responses are DERIVED here from the
        agent payloads: every reviewer payload (all rounds, in order) for
        ``reviews_response``, the LAST round's payload for the singleton roles —
        the same semantics the LangGraph state applies while running."""
        agent_records = [
            Adapter.to_agent_record(row, traces.get(row.agent_trace_id) if row.agent_trace_id is not None else None)
            for row in agent_rows
        ]
        reviews = [r.response_payload for r in agent_records if r.agent_role is AgentRole.REVIEWER]
        return GraphReviewRecord(
            run_id=run_row.run_id,
            timestamp=run_row.timestamp,
            paper_id=run_row.paper_id,
            description=run_row.description,
            decision=run_row.decision,
            total_rounds=run_row.total_rounds,
            reviews_response=reviews or None,
            meta_review_response=Adapter._last_payload(agent_records, AgentRole.META_REVIEWER),
            area_chair_response=Adapter._last_payload(agent_records, AgentRole.AREA_CHAIR),
            author_response=Adapter._last_payload(agent_records, AgentRole.AUTHOR_AGENT),
            graph_config=run_row.graph_config,
            agent_records=agent_records,
        )

    @staticmethod
    def to_agent_record(row: GraphReviewAgentTable, trace: AgentTraceTable | None) -> AgentResponseRecord:
        """``graph_review_agent`` row (+ its ``agent_trace``) -> ``AgentResponseRecord``:
        identity/round from the agent row, everything verbatim from the trace."""
        return AgentResponseRecord(
            agent_role=AgentRole(row.agent_role),
            agent_index=row.agent_index,
            round=row.round,
            input_message=trace.input_message if trace else None,
            context_used=trace.context_used if trace else None,
            response_payload=trace.response_payload if trace else {},
            system_prompt=trace.system_prompt if trace else None,
            input_tokens=trace.input_tokens if trace else None,
            output_tokens=trace.output_tokens if trace else None,
            total_tokens=trace.total_tokens if trace else None,
        )

    @staticmethod
    def _last_payload(agent_records: list[AgentResponseRecord], role: AgentRole) -> dict | None:
        """The payload of the role's most recent invocation (rows are in
        insertion order), None when the role never ran."""
        payloads = [r.response_payload for r in agent_records if r.agent_role is role]
        return payloads[-1] if payloads else None

    @staticmethod
    def to_papers(rows: list[PaperTable]) -> list[Paper]:
        return [Adapter.to_paper(row) for row in rows]

    @staticmethod
    def to_authors(pairs: list[tuple[AuthorTable, int]]) -> list[Author]:
        return [Adapter.to_author(row, position) for row, position in pairs]

    @staticmethod
    def to_prompts(rows: list[PromptVersionTable]) -> list[PromptVersion]:
        return [Adapter.to_prompt(row) for row in rows]

    @staticmethod
    def to_instructions(rows: list[PromptInstructionTable]) -> list[PromptInstruction]:
        return [Adapter.to_instruction(row) for row in rows]

    @staticmethod
    def to_run_summaries(rows: list[GraphReviewTable]) -> list[GraphReviewSummary]:
        return [Adapter.to_run_summary(row) for row in rows]

    @staticmethod
    def to_agent_records(pairs: list[tuple[GraphReviewAgentTable, AgentTraceTable | None]]) -> list[AgentResponseRecord]:
        return [Adapter.to_agent_record(row, trace) for row, trace in pairs]


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def build_paper_id(paper_type: PaperType, file_name: str) -> str:
        """Catalog id in the form ``<paper-type>_<name>_<extension>``
        (e.g. ``other_attention_pdf``). ``file_name`` may be a bare name or a
        relative path; directories and the extension dot are dropped."""
        path = PurePosixPath(str(file_name).replace("\\", "/"))
        extension = path.suffix.lstrip(".").lower()
        parts = [paper_type.value.lower(), path.stem]
        if extension:
            parts.append(extension)
        return "_".join(parts)

    @staticmethod
    def to_paper_row(paper: Paper) -> PaperTable:
        """Build a new ``PaperTable`` row from a ``Paper`` (``id`` DB-generated)."""
        paper_id = Factory.build_paper_id(paper.paper_type, paper.paper_name)
        return PaperTable(
            paper_id=paper_id,
            paper_name=paper.paper_name,
            paper_type=paper.paper_type.value,
            description=paper.description,
            open_review_id=paper.open_review_id,
            conference=paper.conference,
            openreview_api_version=paper.openreview_api_version,
            human_decision=paper.human_decision,
            num_graph_review=paper.num_graph_review,
        )

    @staticmethod
    def to_author_row(author: Author) -> AuthorTable:
        """Build a new ``AuthorTable`` row from an ``Author`` (``id`` DB-generated;
        ``position`` belongs to the paper_author link, not to this row)."""
        return AuthorTable(
            full_name=author.full_name,
            email=author.email,
            affiliation=author.affiliation,
            openreview_profile_id=author.openreview_profile_id,
        )

    @staticmethod
    def to_run_rows(record: GraphReviewRecord) -> tuple[GraphReviewTable, list[AgentRecordPair]]:
        """Every row for one run in a single call — the write-side mirror of
        ``Adapter.to_run_record``: ``save_run`` unpacks this straight into
        ``DbRunRepository.save_rows``. No run-level payload row: the responses
        live once in the agent traces."""
        return (
            Factory.to_run_row(record),
            Factory.to_agent_record_pairs(record.run_id, record.agent_records),
        )

    @staticmethod
    def to_run_row(record: GraphReviewRecord) -> GraphReviewTable:
        """Build the ``graph_review`` facts row (``meta_overall_score`` /
        ``max_rounds`` extracted from the meta-review payload / graph config)."""
        return GraphReviewTable(
            run_id=record.run_id,
            timestamp=record.timestamp,
            paper_id=record.paper_id,
            description=record.description,
            decision=record.decision,
            total_rounds=record.total_rounds,
            max_rounds=record.graph_config.get("max_rounds"),
            meta_overall_score=(record.meta_review_response or {}).get("overall_score"),
            graph_config=record.graph_config,
        )

    @staticmethod
    def to_agent_record_row(run_id: str, agent_record: AgentResponseRecord) -> GraphReviewAgentTable:
        """Build one ``graph_review_agent`` facts row (rating/confidence/
        overall_score/decision extracted from the payload). ``agent_trace_id``
        is linked by the repository after the trace row is flushed."""
        payload = agent_record.response_payload
        return GraphReviewAgentTable(
            run_id=run_id,
            agent_role=str(agent_record.agent_role),
            agent_index=agent_record.agent_index,
            round=agent_record.round,
            rating=payload.get("rating"),
            confidence=payload.get("confidence"),
            overall_score=payload.get("overall_score"),
            decision=payload.get("decision") or payload.get("recommendation"),
        )

    @staticmethod
    def to_agent_trace_row(run_id: str, agent_record: AgentResponseRecord) -> AgentTraceTable:
        """Build one ``agent_trace`` row — the verbatim invocation trace."""
        return AgentTraceTable(
            run_id=run_id,
            input_message=agent_record.input_message,
            system_prompt=agent_record.system_prompt,
            context_used=agent_record.context_used,
            response_payload=agent_record.response_payload,
            input_tokens=agent_record.input_tokens,
            output_tokens=agent_record.output_tokens,
            total_tokens=agent_record.total_tokens,
            latency_seconds=agent_record.latency_seconds
        )

    @staticmethod
    def to_agent_record_pairs(run_id: str, agent_records: list[AgentResponseRecord]) -> list[AgentRecordPair]:
        """Build the (facts row, trace row) pair for every agent invocation."""
        return [
            (Factory.to_agent_record_row(run_id, agent_record), Factory.to_agent_trace_row(run_id, agent_record))
            for agent_record in agent_records
        ]
