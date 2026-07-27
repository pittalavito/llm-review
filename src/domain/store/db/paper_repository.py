"""Repository for the paper catalog (persistence rows: PaperTable).

The DB is the source of truth for the paper list at runtime. ``seed`` registers
the paper paths supplied by the files store as OTHER; num_review is refreshed
from the run count on (re)seed. Row -> domain translation is the StoreService's
job.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import func
from sqlmodel import Session, select

from domain.store.db.repository import SqlRepository
from domain.store.db.models import PaperTable, ReviewRunTable
from domain.models.paper import PaperType


class DbPaperRepository(SqlRepository[PaperTable]):

    def __init__(self):
        super().__init__(PaperTable)

    def list(self) -> list[PaperTable]:
        with self._session() as session:
            return list(session.exec(select(PaperTable).order_by(PaperTable.paper_path)).all())

    def list_paths(self) -> list[str]:
        with self._session() as session:
            return list(session.exec(select(PaperTable.paper_path).order_by(PaperTable.paper_path)).all())

    def list_openreview(self) -> list[PaperTable]:
        with self._session() as session:
            return list(session.exec(
                select(PaperTable)
                .where(PaperTable.paper_type == PaperType.OPEN_REVIEW.value)
                .order_by(PaperTable.paper_path)
            ).all())

    def get_by_path(self, paper_path: str) -> PaperTable | None:
        with self._session() as session:
            return session.exec(select(PaperTable).where(PaperTable.paper_path == paper_path)).first()

    def create(self, row: PaperTable) -> PaperTable | None:
        """Insert a new paper row. Returns None if paper_path already exists."""
        with self._session() as session:
            duplicate = session.exec(
                select(PaperTable.id).where(PaperTable.paper_path == row.paper_path)
            ).first()
            if duplicate is not None:
                return None
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def seed(self, paper_paths: list[str]) -> int:
        """Register the given paper paths (from the files store) as OTHER
        (idempotent); existing rows only get their num_review snapshot refreshed.
        Returns the number inserted."""
        inserted = 0
        with self._session() as session:
            existing = {row.paper_path: row for row in session.exec(select(PaperTable)).all()}
            counts = self._run_counts(session)
            for paper_path in paper_paths:
                row = existing.get(paper_path)
                if row is None:
                    session.add(PaperTable(**self._fields_from(paper_path, counts.get(paper_path, 0))))
                    inserted += 1
                else:
                    row.num_review = counts.get(paper_path, 0)
                    session.add(row)
            session.commit()
        return inserted

    @staticmethod
    def _fields_from(paper_path: str, run_count: int) -> dict:
        return {
            "paper_path": paper_path,
            "paper_name": Path(paper_path).stem,
            "paper_type": PaperType.OTHER.value,
            "num_review": run_count,
        }

    @staticmethod
    def _run_counts(session: Session) -> dict[str, int]:
        rows = session.exec(
            select(ReviewRunTable.paper_path, func.count()).group_by(ReviewRunTable.paper_path)
        ).all()
        return {paper_path: count for paper_path, count in rows}
