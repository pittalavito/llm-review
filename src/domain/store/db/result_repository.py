"""Run persistence at the row level: facts in review_run / review_agent_run,
verbatim payloads in the 1:1 review_run_payload / review_agent_run_payload
tables. The repository only reads and writes ``*Table`` rows — building them
from / into RunRecord is the StoreService's job. Error-agnostic: reads return
None when the run is absent.

Note: review_agent_config (the normalized graph config) is not populated yet —
it needs the graph-config model, which does not exist in this project yet.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from config import Config
from domain.store.db.repository import SqlRepository
from domain.store.db.models import (
    PaperTable,
    ReviewAgentRunPayloadTable,
    ReviewAgentRunTable,
    ReviewRunPayloadTable,
    ReviewRunTable,
)

AgentPair = tuple[ReviewAgentRunTable, ReviewAgentRunPayloadTable]
RunRows = tuple[ReviewRunTable, ReviewRunPayloadTable | None, list[ReviewAgentRunTable], dict[int, ReviewAgentRunPayloadTable | None]]


class DbResultRepository(SqlRepository[ReviewRunTable]):

    def __init__(self, config: Config):
        super().__init__(config, ReviewRunTable)

    @staticmethod
    def build_run_id(paper_path: str) -> str:
        """Build a run_id from the current timestamp and the paper filename."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
        stem = Path(paper_path).stem
        safe = re.sub(r"[^\w\-]", "_", stem)[:40]
        return f"{ts}_{safe}"

    def save_rows(self, run_row: ReviewRunTable, payload_row: ReviewRunPayloadTable, agent_pairs: list[AgentPair]) -> str:
        """Persist the pre-built rows for one run. Saving an existing run_id
        replaces it (the FK cascade removes the old children). The agent
        payload's FK is assigned here, after the agent row is flushed."""
        run_id = run_row.run_id  # capture before commit expires the row
        with self._session() as session:
            existing = session.get(ReviewRunTable, run_row.run_id)
            if existing is not None:
                session.delete(existing)
                session.flush()

            session.add(run_row)
            session.flush()
            session.add(payload_row)

            for agent_row, agent_payload in agent_pairs:
                session.add(agent_row)
                session.flush()  # need agent_row.id for the payload FK
                agent_payload.agent_run_id = agent_row.id
                session.add(agent_payload)

            self._refresh_paper_num_review(session, run_row.paper_path)
            session.commit()
        return run_id

    def list_summaries(self) -> list[ReviewRunTable]:
        """All run rows, most recent first (facts only)."""
        statement = select(ReviewRunTable).order_by(ReviewRunTable.run_id.desc())
        with self._session() as session:
            return list(session.exec(statement).all())

    def get_rows(self, run_id: str) -> RunRows | None:
        """The run row, its payload row, its agent rows and their payloads
        (keyed by agent-run id). None if the run is absent."""
        with self._session() as session:
            run_row = session.get(ReviewRunTable, run_id)
            if run_row is None:
                return None
            payload = session.get(ReviewRunPayloadTable, run_id)
            agent_rows = list(session.exec(
                select(ReviewAgentRunTable)
                .where(ReviewAgentRunTable.run_id == run_id)
                .order_by(ReviewAgentRunTable.id)
            ).all())
            agent_payloads = {r.id: session.get(ReviewAgentRunPayloadTable, r.id) for r in agent_rows}
        return run_row, payload, agent_rows, agent_payloads

    def get_agent_run_rows(self, run_id: str, agent: str | None = None, round_index: int | None = None) -> list[AgentPair] | None:
        """Agent rows + payloads for a run, filtered in SQL. None if the run is
        absent."""
        with self._session() as session:
            if session.get(ReviewRunTable, run_id) is None:
                return None
            statement = select(ReviewAgentRunTable).where(ReviewAgentRunTable.run_id == run_id)
            if agent is not None:
                statement = statement.where(ReviewAgentRunTable.agent == agent)
            if round_index is not None:
                statement = statement.where(ReviewAgentRunTable.round == round_index)
            rows = list(session.exec(statement.order_by(ReviewAgentRunTable.id)).all())
            payloads = {r.id: session.get(ReviewAgentRunPayloadTable, r.id) for r in rows}
        return [(row, payloads.get(row.id)) for row in rows]

    def list_run_ids_for_paper(self, paper_path: str) -> list[str]:
        """Run ids for a paper, most recent first."""
        with self._session() as session:
            return list(session.exec(
                select(ReviewRunTable.run_id)
                .where(ReviewRunTable.paper_path == paper_path)
                .order_by(ReviewRunTable.run_id.desc())
            ).all())

    @staticmethod
    def _refresh_paper_num_review(session: Session, paper_path: str) -> None:
        """Keep paper.num_review in sync with the run count for the paper.
        No-op when the paper is not (yet) in the catalog."""
        paper = session.exec(select(PaperTable).where(PaperTable.paper_path == paper_path)).first()
        if paper is None:
            return
        count = session.exec(
            select(func.count()).select_from(ReviewRunTable).where(ReviewRunTable.paper_path == paper_path)
        ).one()
        paper.num_review = int(count)
        session.add(paper)
