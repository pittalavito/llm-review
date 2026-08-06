"""Run persistence at the row level: facts in graph_review / graph_review_agent.
The verbatim traces live in Redis (keyspace agent-trace, one bundle per run,
referenced by ``trace_index`` on the agent rows) — persisting and reading them
is the StoreService's job, like building rows from / into GraphReviewRecord.
Error-agnostic: reads return None when the run is absent.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlmodel import Session, select

from domain.store.db.repository import SqlRepository
from models.store.db import GraphReviewAgentTable, GraphReviewTable, PaperTable

RunRows = tuple[GraphReviewTable, list[GraphReviewAgentTable]]


class DbRunRepository(SqlRepository[GraphReviewTable]):

    def __init__(self):
        super().__init__(GraphReviewTable)

    @staticmethod
    def build_run_id(paper_id: str) -> str:
        """Build a run_id from the current timestamp and the paper id (already
        a safe slug — no stem/sanitize needed)."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        return f"{ts}_{paper_id}"

    def save_rows(self, run_row: GraphReviewTable, agent_rows: list[GraphReviewAgentTable]) -> str:
        """Persist the pre-built rows for one run. Saving an existing run_id
        replaces it (the FK cascade removes the old agent rows)."""
        run_id = run_row.run_id
        with self._session() as session:
            existing = session.get(GraphReviewTable, run_row.run_id)
            if existing is not None:
                session.delete(existing)
                session.flush()

            session.add(run_row)
            session.flush()

            for agent_row in agent_rows:
                session.add(agent_row)

            self._refresh_paper_num_graph_review(session, run_row.paper_id)
            session.commit()
        return run_id

    def list_summaries(self) -> list[GraphReviewTable]:
        """All run rows, most recent first (facts only)."""
        statement = select(GraphReviewTable).order_by(GraphReviewTable.run_id.desc())
        with self._session() as session:
            return list(session.exec(statement).all())

    def get_rows(self, run_id: str) -> RunRows | None:
        """The run row and its agent rows, in insertion order. None if the run
        is absent."""
        with self._session() as session:
            run_row = session.get(GraphReviewTable, run_id)
            if run_row is None:
                return None
            agent_rows = list(session.exec(
                select(GraphReviewAgentTable)
                .where(GraphReviewAgentTable.run_id == run_id)
                .order_by(GraphReviewAgentTable.id)
            ).all())
        return run_row, agent_rows

    def list_run_ids_for_paper(self, paper_id: str) -> list[str]:
        """Run ids for a paper, most recent first."""
        with self._session() as session:
            return list(session.exec(
                select(GraphReviewTable.run_id)
                .where(GraphReviewTable.paper_id == paper_id)
                .order_by(GraphReviewTable.run_id.desc())
            ).all())

    @staticmethod
    def _refresh_paper_num_graph_review(session: Session, paper_id: str) -> None:
        """Keep paper.num_graph_review in sync with the run count for the paper.
        No-op when the paper is not (yet) in the catalog."""
        paper = session.exec(select(PaperTable).where(PaperTable.paper_id == paper_id)).first()
        if paper is None:
            return
        count = session.exec(
            select(func.count()).select_from(GraphReviewTable).where(GraphReviewTable.paper_id == paper_id)
        ).one()
        paper.num_graph_review = int(count)
        session.add(paper)
