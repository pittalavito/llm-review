"""DB store facade: one import point for the DB persistence layer.

Re-exports the DB repositories and holds the two DB translation seams as
static-method classes: ``Adapter`` (rows -> domain models, reads) and ``Factory``
(domain models -> rows, writes).
"""
from domain.store.db.paper_repository import DbPaperRepository
from domain.store.db.prompt_repository import DbPromptRepository
from domain.store.db.result_repository import DbResultRepository

from domain.models.agent import AgentRole
from domain.models.paper import Paper, PaperType
from domain.models.prompt import PromptVersion
from domain.models.run_record import AgentRun, RunRecord, RunSummary
from domain.store.db.models import (
    PaperTable,
    PromptVersionTable,
    ReviewAgentRunPayloadTable,
    ReviewAgentRunTable,
    ReviewRunPayloadTable,
    ReviewRunTable,
)


__all__ = ["DbPaperRepository", "DbPromptRepository", "DbResultRepository", "Adapter", "Factory"]


class Adapter:
    """Read seam: DB rows -> domain models."""

    @staticmethod
    def to_paper(row: PaperTable) -> Paper:
        """``PaperTable`` row -> ``Paper`` (``decision`` -> ``human_decision``,
        ``num_review`` -> ``num_app_review``, ``paper_type`` str -> ``PaperType``)."""
        return Paper(
            id=row.id,
            paper_path=row.paper_path,
            paper_name=row.paper_name,
            paper_type=PaperType(row.paper_type),
            open_review_id=row.open_review_id,
            conference=row.conference,
            openreview_api_version=row.openreview_api_version,
            human_decision=row.decision,
            num_app_review=row.num_review,
        )

    @staticmethod
    def to_prompt(row: PromptVersionTable) -> PromptVersion:
        """``PromptVersionTable`` row -> ``PromptVersion`` (field-for-field)."""
        return PromptVersion.model_validate(row.model_dump())

    @staticmethod
    def to_run_summary(row: ReviewRunTable) -> RunSummary:
        """``review_run`` row -> lightweight ``RunSummary`` (facts only)."""
        return RunSummary(
            run_id=row.run_id,
            timestamp=row.timestamp,
            paper_path=row.paper_path,
            run_description=row.run_description,
            decision=row.decision,
            total_rounds=row.total_rounds,
        )

    @staticmethod
    def to_run_record(
        run_row: ReviewRunTable,
        payload: ReviewRunPayloadTable | None,
        agent_rows: list[ReviewAgentRunTable],
        agent_payloads: dict[int, ReviewAgentRunPayloadTable | None],
    ) -> RunRecord:
        """Reassemble a full ``RunRecord`` from its run row, payload row, agent
        rows and their payloads. A missing payload degrades to empty/None."""
        return RunRecord(
            run_id=run_row.run_id,
            timestamp=run_row.timestamp,
            paper_path=run_row.paper_path,
            run_description=run_row.run_description,
            decision=run_row.decision,
            total_rounds=run_row.total_rounds,
            reviews=payload.reviews if payload else None,
            meta_review=payload.meta_review if payload else None,
            area_chair_response=payload.area_chair_response if payload else None,
            author_response=payload.author_response if payload else None,
            retrieval_metadata=payload.retrieval_metadata if payload else None,
            graph_config=payload.graph_config if payload else {},
            agent_runs=[Adapter.to_agent_run(row, agent_payloads.get(row.id)) for row in agent_rows],
        )

    @staticmethod
    def to_agent_run(row: ReviewAgentRunTable, payload: ReviewAgentRunPayloadTable | None) -> AgentRun:
        """``review_agent_run`` row (+ payload) -> ``AgentRun``."""
        return AgentRun(
            agent_role=AgentRole(row.agent_role),
            agent_index=row.agent_index,
            round=row.round,
            input_message=row.input_message,
            context_used=row.context_used,
            response_payload=payload.response_payload if payload else {},
            prompt_trace=payload.prompt_trace if payload else None,
            runtime_trace=payload.runtime_trace if payload else None,
        )

    @staticmethod
    def to_papers(rows: list[PaperTable]) -> list[Paper]:
        return [Adapter.to_paper(row) for row in rows]

    @staticmethod
    def to_prompts(rows: list[PromptVersionTable]) -> list[PromptVersion]:
        return [Adapter.to_prompt(row) for row in rows]

    @staticmethod
    def to_run_summaries(rows: list[ReviewRunTable]) -> list[RunSummary]:
        return [Adapter.to_run_summary(row) for row in rows]

    @staticmethod
    def to_agent_runs(pairs: list[tuple[ReviewAgentRunTable, ReviewAgentRunPayloadTable | None]]) -> list[AgentRun]:
        return [Adapter.to_agent_run(row, payload) for row, payload in pairs]


class Factory:
    """Write seam: domain models -> DB rows."""

    @staticmethod
    def to_paper_row(paper: Paper) -> PaperTable:
        """Build a new ``PaperTable`` row from a ``Paper`` (``id`` DB-generated)."""
        return PaperTable(
            paper_path=paper.paper_path,
            paper_name=paper.paper_name,
            paper_type=paper.paper_type.value,
            open_review_id=paper.open_review_id,
            conference=paper.conference,
            openreview_api_version=paper.openreview_api_version,
            decision=paper.human_decision,
            num_review=paper.num_app_review,
        )

    @staticmethod
    def to_run_row(record: RunRecord) -> ReviewRunTable:
        """Build the ``review_run`` facts row (``meta_overall_score`` / ``max_rounds``
        extracted from the meta-review payload / graph config)."""
        return ReviewRunTable(
            run_id=record.run_id,
            timestamp=record.timestamp,
            paper_path=record.paper_path,
            run_description=record.run_description,
            decision=record.decision,
            total_rounds=record.total_rounds,
            max_rounds=record.graph_config.get("max_rounds"),
            meta_overall_score=(record.meta_review or {}).get("overall_score"),
        )

    @staticmethod
    def to_run_payload_row(record: RunRecord) -> ReviewRunPayloadTable:
        """Build the ``review_run_payload`` row (verbatim LLM payloads)."""
        return ReviewRunPayloadTable(
            run_id=record.run_id,
            reviews=record.reviews,
            meta_review=record.meta_review,
            area_chair_response=record.area_chair_response,
            author_response=record.author_response,
            retrieval_metadata=record.retrieval_metadata,
            graph_config=record.graph_config,
        )

    @staticmethod
    def to_agent_row(run_id: str, agent_run: AgentRun) -> ReviewAgentRunTable:
        """Build one ``review_agent_run`` facts row (rating/confidence/overall_score/
        decision, latency and token counts extracted from payload and trace)."""
        payload = agent_run.response_payload
        runtime = agent_run.runtime_trace or {}
        return ReviewAgentRunTable(
            run_id=run_id,
            agent_role=str(agent_run.agent_role),
            agent_index=agent_run.agent_index,
            round=agent_run.round,
            input_message=agent_run.input_message,
            context_used=agent_run.context_used,
            rating=payload.get("rating"),
            confidence=payload.get("confidence"),
            overall_score=payload.get("overall_score"),
            decision=payload.get("decision") or payload.get("recommendation"),
            latency_ms=runtime.get("latency_ms"),
            input_tokens=runtime.get("input_tokens"),
            output_tokens=runtime.get("output_tokens"),
            total_tokens=runtime.get("total_tokens"),
        )

    @staticmethod
    def to_agent_payload_row(agent_run: AgentRun) -> ReviewAgentRunPayloadTable:
        """Build one ``review_agent_run_payload`` row. The ``agent_run_id`` FK is
        assigned by the repository after the parent agent row is flushed."""
        return ReviewAgentRunPayloadTable(
            response_payload=agent_run.response_payload,
            prompt_trace=agent_run.prompt_trace,
            runtime_trace=agent_run.runtime_trace,
        )

    @staticmethod
    def to_agent_pairs(run_id: str, agent_runs: list[AgentRun]) -> list[tuple[ReviewAgentRunTable, ReviewAgentRunPayloadTable]]:
        """Build the (facts row, payload row) pair for every agent invocation."""
        return [(Factory.to_agent_row(run_id, agent_run), Factory.to_agent_payload_row(agent_run)) for agent_run in agent_runs]
