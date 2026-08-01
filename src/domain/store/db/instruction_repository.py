"""CRUD repository for persona prompt instructions (persistence rows:
PromptInstructionTable). Instructions are immutable like prompt versions:
create() adds rows, update_meta() may only touch description and is_active.
Error-agnostic: a miss or a duplicate returns None. Row -> domain translation
is the StoreService's job.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from core.observability import LogPrefix, log_warning
from domain.store.db.repository import SqlRepository
from models.store.db import PromptInstructionTable


class DbInstructionRepository(SqlRepository[PromptInstructionTable]):

    def __init__(self):
        super().__init__(PromptInstructionTable)

    def list_by_labels(self, labels: list[str]) -> list[PromptInstructionTable]:
        with self._session() as session:
            return list(session.exec(
                select(PromptInstructionTable).where(PromptInstructionTable.label.in_(labels))
            ).all())

    def list(self, type: str | None = None, include_inactive: bool = False) -> list[PromptInstructionTable]:
        statement = select(PromptInstructionTable)
        if type is not None:
            statement = statement.where(PromptInstructionTable.type == type)
        if not include_inactive:
            statement = statement.where(PromptInstructionTable.is_active == True)
        statement = statement.order_by(PromptInstructionTable.type, PromptInstructionTable.label)
        with self._session() as session:
            return list(session.exec(statement).all())

    def create(self, type: str, label: str, instruction: str, description: str | None = None, agent_role: str | None = None) -> PromptInstructionTable | None:
        """Register a new immutable instruction. Returns None if (type, label)
        already exists."""
        with self._session() as session:
            duplicate = session.exec(
                select(PromptInstructionTable.id).where(
                    PromptInstructionTable.type == type,
                    PromptInstructionTable.label == label,
                )
            ).first()
            if duplicate is not None:
                log_warning(LogPrefix.PROMPT_REPOSITORY, f"Prompt instruction already exists: {type}/{label}")
                return None
            row = PromptInstructionTable(
                type=type,
                label=label,
                instruction=instruction,
                description=description,
                agent_role=agent_role,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def update_meta(self, instruction_id: int, description: str | None = None, is_active: bool | None = None) -> PromptInstructionTable | None:
        """Update mutable metadata only — the instruction text never changes.
        Returns None if the instruction does not exist."""
        with self._session() as session:
            row = session.get(PromptInstructionTable, instruction_id)
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

    def seed_defaults(self, seeds: list[tuple[str, str, str, str, str]]) -> int:
        """Insert the code-shipped instructions missing from the registry —
        idempotent upsert by (type, label), never overwrites existing rows.
        Returns the number inserted."""
        inserted = 0
        with self._session() as session:
            existing = {
                (row.type, row.label)
                for row in session.exec(
                    select(PromptInstructionTable.type, PromptInstructionTable.label)
                ).all()
            }
            now = datetime.now(timezone.utc).isoformat()
            for type, label, instruction, description, agent_role in seeds:
                if (str(type), label) in existing:
                    continue
                session.add(PromptInstructionTable(
                    type=str(type),
                    label=label,
                    instruction=instruction,
                    description=description,
                    agent_role=agent_role,
                    created_at=now,
                ))
                inserted += 1
            session.commit()
        return inserted
