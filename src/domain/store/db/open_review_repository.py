"""Repository for OpenReview parsed data (OpenReviewTable)."""
from __future__ import annotations

from sqlmodel import select

from domain.store.db.repository import SqlRepository
from models.store.db import OpenReviewTable


class DbOpenReviewRepository(SqlRepository[OpenReviewTable]):

    def __init__(self):
        super().__init__(OpenReviewTable)

    def list_by_paper(self, paper_id: str) -> list[OpenReviewTable]:
        """Get all reviews for a paper."""
        with self._session() as session:
            return list(session.exec(
                select(OpenReviewTable)
                .where(OpenReviewTable.paper_id == paper_id)
                .order_by(OpenReviewTable.created_at)
            ).all())

    def create_batch(self, rows: list[OpenReviewTable]) -> list[OpenReviewTable]:
        """Insert multiple review records for a paper."""
        if not rows:
            return []
        with self._session() as session:
            session.add_all(rows)
            session.commit()
            for row in rows:
                session.refresh(row)
            return rows

    def delete_by_paper(self, paper_id: str) -> int:
        """Delete all reviews for a paper (e.g., before re-import). Returns count."""
        with self._session() as session:
            count = session.exec(
                select(OpenReviewTable)
                .where(OpenReviewTable.paper_id == paper_id)
            ).all()
            for row in count:
                session.delete(row)
            session.commit()
            return len(count)
