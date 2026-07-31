"""Repository for the paper catalog (persistence rows: PaperTable).

The DB is the source of truth for the paper list at runtime. Rows are created
via ``create`` with the ``paper_id`` already built by the store Factory
(``<paper-type>_<name>_<extension>``); the file itself lives in the files store
under the same id. Row -> domain translation is the StoreService's job.
"""
from __future__ import annotations

from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.domain.paper import PaperType
from models.store.db import PaperTable


class DbPaperRepository(SqlRepository[PaperTable]):

    def __init__(self):
        super().__init__(PaperTable)

    def list(self) -> list[PaperTable]:
        with self._session() as session:
            return list(session.exec(select(PaperTable).order_by(PaperTable.paper_id)).all())

    def list_ids(self) -> list[str]:
        with self._session() as session:
            return list(session.exec(select(PaperTable.paper_id).order_by(PaperTable.paper_id)).all())

    def list_openreview(self) -> list[PaperTable]:
        with self._session() as session:
            return list(session.exec(
                select(PaperTable)
                .where(PaperTable.paper_type == PaperType.OPEN_REVIEW.value)
                .order_by(PaperTable.paper_id)
            ).all())

    def get_by_id(self, paper_id: str) -> PaperTable | None:
        with self._session() as session:
            return session.exec(select(PaperTable).where(PaperTable.paper_id == paper_id)).first()

    def create(self, row: PaperTable) -> PaperTable | None:
        """Insert a new paper row. Returns None if paper_id already exists."""
        with self._session() as session:
            duplicate = session.exec(
                select(PaperTable.id).where(PaperTable.paper_id == row.paper_id)
            ).first()
            if duplicate is not None:
                return None
            session.add(row)
            session.commit()
            session.refresh(row)
            return row