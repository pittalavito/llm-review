"""Repository for the author catalog (persistence rows: AuthorTable) and the
paper <-> author bridge (PaperAuthorTable).

Authors are shared across papers: ``get_or_create`` deduplicates by
``openreview_profile_id`` when present, by (full_name, email) otherwise.
Row -> domain translation is the StoreService's job.
"""
from __future__ import annotations

from sqlmodel import Session, select

from domain.store.db.repository import SqlRepository
from models.store.db import AuthorTable, PaperAuthorTable


class DbAuthorRepository(SqlRepository[AuthorTable]):

    def __init__(self):
        super().__init__(AuthorTable)

    def get_or_create(self, row: AuthorTable) -> AuthorTable:
        """The existing author matching ``row`` (see dedup rules above), or the
        freshly inserted row when there is no match."""
        with self._session() as session:
            existing = self._find_existing(session, row)
            if existing is not None:
                return existing
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def link_to_paper(self, paper_id: str, author_id: int, position: int) -> PaperAuthorTable:
        """Link the author to the paper at ``position`` (1-based). Idempotent:
        an existing link is returned as-is (position unchanged)."""
        with self._session() as session:
            existing = session.exec(
                select(PaperAuthorTable).where(
                    PaperAuthorTable.paper_id == paper_id,
                    PaperAuthorTable.author_id == author_id,
                )
            ).first()
            if existing is not None:
                return existing
            link = PaperAuthorTable(paper_id=paper_id, author_id=author_id, position=position)
            session.add(link)
            session.commit()
            session.refresh(link)
            return link

    def list_for_paper(self, paper_id: str) -> list[tuple[AuthorTable, int]]:
        """The paper's authors as (author row, position), ordered by position."""
        with self._session() as session:
            rows = session.exec(
                select(AuthorTable, PaperAuthorTable.position)
                .join(PaperAuthorTable, PaperAuthorTable.author_id == AuthorTable.id)
                .where(PaperAuthorTable.paper_id == paper_id)
                .order_by(PaperAuthorTable.position)
            ).all()
            return [(author, position) for author, position in rows]

    def list_papers_for_author(self, author_id: int) -> list[str]:
        """The paper_ids the author is linked to."""
        with self._session() as session:
            return list(session.exec(
                select(PaperAuthorTable.paper_id)
                .where(PaperAuthorTable.author_id == author_id)
                .order_by(PaperAuthorTable.paper_id)
            ).all())

    @staticmethod
    def _find_existing(session: Session, row: AuthorTable) -> AuthorTable | None:
        if row.openreview_profile_id:
            found = session.exec(
                select(AuthorTable).where(AuthorTable.openreview_profile_id == row.openreview_profile_id)
            ).first()
            if found is not None:
                return found
        return session.exec(
            select(AuthorTable).where(
                AuthorTable.full_name == row.full_name,
                AuthorTable.email == row.email,
            )
        ).first()
