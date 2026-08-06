"""CRUD repository for system-prompt presets (persistence rows:
SystemPromptPresetTable). Unlike prompt versions and instructions a preset is
a mutable SELECTION: update() may change every field. Error-agnostic: a miss
or a duplicate returns None. Row -> domain translation is the StoreService's
job.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import select

from core.observability import LogPrefix, log_warning
from domain.store.db.repository import SqlRepository
from models.store.db import SystemPromptPresetTable


class DbPresetRepository(SqlRepository[SystemPromptPresetTable]):

    def __init__(self):
        super().__init__(SystemPromptPresetTable)

    def list(self, agent_role: str | None = None, include_inactive: bool = False) -> list[SystemPromptPresetTable]:
        statement = select(SystemPromptPresetTable)
        if agent_role is not None:
            statement = statement.where(SystemPromptPresetTable.agent_role == agent_role)
        if not include_inactive:
            statement = statement.where(SystemPromptPresetTable.is_active == True)
        statement = statement.order_by(SystemPromptPresetTable.agent_role, SystemPromptPresetTable.name)
        with self._session() as session:
            return list(session.exec(statement).all())

    def create(self, agent_role: str, name: str, base_prompt_version: str, instruction_ids: list[int] | None = None, description: str | None = None) -> SystemPromptPresetTable | None:
        """Register a new preset. Returns None if (agent_role, name) already
        exists."""
        with self._session() as session:
            duplicate = session.exec(
                select(SystemPromptPresetTable.id).where(
                    SystemPromptPresetTable.agent_role == agent_role,
                    SystemPromptPresetTable.name == name,
                )
            ).first()
            if duplicate is not None:
                log_warning(LogPrefix.PROMPT_REPOSITORY, f"System prompt preset already exists: {agent_role}/{name}")
                return None
            row = SystemPromptPresetTable(
                agent_role=agent_role,
                name=name,
                base_prompt_version=base_prompt_version,
                instruction_ids=list(instruction_ids or []),
                description=description,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def seed_defaults(self, seeds: list[tuple[str, str, str, list[int], str]]) -> int:
        """Insert the code-shipped presets missing from the registry —
        idempotent upsert by (agent_role, name), never overwrites existing
        rows. ``instruction_ids`` are already resolved by the caller (the
        seeds declare instructions by natural key). Returns the number
        inserted."""
        inserted = 0
        with self._session() as session:
            existing = {
                (row_role, row_name)
                for row_role, row_name in session.exec(
                    select(SystemPromptPresetTable.agent_role, SystemPromptPresetTable.name)
                ).all()
            }
            now = datetime.now(timezone.utc).isoformat()
            for agent_role, name, base_prompt_version, instruction_ids, description in seeds:
                if (agent_role, name) in existing:
                    continue
                session.add(SystemPromptPresetTable(
                    agent_role=agent_role,
                    name=name,
                    base_prompt_version=base_prompt_version,
                    instruction_ids=list(instruction_ids),
                    description=description,
                    created_at=now,
                ))
                inserted += 1
            session.commit()
        return inserted

    def update(self, preset_id: int, name: str | None = None, description: str | None = None, base_prompt_version: str | None = None, instruction_ids: list[int] | None = None, is_active: bool | None = None) -> SystemPromptPresetTable | None:
        """Update any field — presets are mutable selections. Returns None on a
        miss and on a rename colliding with an existing (agent_role, name)."""
        with self._session() as session:
            row = session.get(SystemPromptPresetTable, preset_id)
            if row is None:
                return None
            if name is not None and name != row.name:
                duplicate = session.exec(
                    select(SystemPromptPresetTable.id).where(
                        SystemPromptPresetTable.agent_role == row.agent_role,
                        SystemPromptPresetTable.name == name,
                        SystemPromptPresetTable.id != preset_id,
                    )
                ).first()
                if duplicate is not None:
                    log_warning(LogPrefix.PROMPT_REPOSITORY, f"System prompt preset already exists: {row.agent_role}/{name}")
                    return None
                row.name = name
            if description is not None:
                row.description = description
            if base_prompt_version is not None:
                row.base_prompt_version = base_prompt_version
            if instruction_ids is not None:
                row.instruction_ids = list(instruction_ids)
            if is_active is not None:
                row.is_active = is_active
            row.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
