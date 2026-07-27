"""CRUD repository for versioned prompt templates (persistence rows:
PromptVersionTable). Versions are immutable: create() adds rows, update_meta()
may only touch description and is_active. Error-agnostic: a miss or a duplicate
returns None. Row -> domain translation is the StoreService's job.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

from sqlmodel import select

from core.observability import observed, LogPrefix, log_warning
from domain.store.db.repository import SqlRepository
from domain.store.db.models import PromptVersionTable


class DbPromptRepository(SqlRepository[PromptVersionTable]):

    def __init__(self):
        super().__init__(PromptVersionTable)

    def list(self, agent_role: str | None = None, include_inactive: bool = False) -> list[PromptVersionTable]:
        statement = select(PromptVersionTable)
        if agent_role is not None:
            statement = statement.where(PromptVersionTable.agent_role == agent_role)
        if not include_inactive:
            statement = statement.where(PromptVersionTable.is_active == True)
        statement = statement.order_by(PromptVersionTable.agent_role, PromptVersionTable.version_label)
        with self._session() as session:
            return list(session.exec(statement).all())

    def get_by_role_label(self, agent_role: str, version_label: str, only_active: bool = True) -> PromptVersionTable | None:
        statement = select(PromptVersionTable).where(
            PromptVersionTable.agent_role == agent_role,
            PromptVersionTable.version_label == version_label,
        )
        with self._session() as session:
            row = session.exec(statement).first()
        if row is None or (only_active and not row.is_active):
            return None
        return row

    def create(self, agent_role: str, version_label: str, template: str, description: str | None = None) -> PromptVersionTable | None:
        """Register a new immutable version. Returns None if (agent_role,
        version_label) already exists."""
        with self._session() as session:
            duplicate = session.exec(
                select(PromptVersionTable.id).where(
                    PromptVersionTable.agent_role == agent_role,
                    PromptVersionTable.version_label == version_label,
                )
            ).first()
            if duplicate is not None:
                log_warning(LogPrefix.PROMPT_REPOSITORY, f"Prompt version already exists: {agent_role}/{version_label}")
                return None
            row = PromptVersionTable(
                agent_role=agent_role,
                version_label=version_label,
                template=template,
                template_hash=sha256(template.encode("utf-8")).hexdigest(),
                description=description,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def update_meta(self, version_id: int, description: str | None = None, is_active: bool | None = None) -> PromptVersionTable | None:
        """Update mutable metadata only — the template never changes. Returns
        None if the version does not exist."""
        with self._session() as session:
            row = session.get(PromptVersionTable, version_id)
            if row is None:
                return None
            if description is not None:
                row.description = description
            if is_active is not None:
                row.is_active = is_active
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def seed_defaults(self, seeds: list[tuple[str, str, str, str]]) -> int:
        """Insert the code-shipped templates missing from the registry. Never
        overwrites existing rows. Returns the number inserted."""
        inserted = 0
        with self._session() as session:
            existing = {
                (row.agent_role, row.version_label)
                for row in session.exec(
                    select(PromptVersionTable.agent_role, PromptVersionTable.version_label)
                ).all()
            }
            now = datetime.now(timezone.utc).isoformat()
            for agent_role, version_label, template, description in seeds:
                if (agent_role, version_label) in existing:
                    continue
                session.add(PromptVersionTable(
                    agent_role=agent_role,
                    version_label=version_label,
                    template=template,
                    template_hash=sha256(template.encode("utf-8")).hexdigest(),
                    description=description,
                    created_at=now,
                ))
                inserted += 1
            session.commit()
        return inserted
