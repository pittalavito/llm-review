"""SQL persistence base for the DB store, in one file: the ``Engine`` (built once
per database URL and shared across repositories) and the ``SqlRepository`` base
every concrete repository extends. Concrete repositories live in their own files
under domain/store/db/.

Schema migrations are intentionally out of scope (no Alembic): the database is
rebuildable from a backup ZIP, so recreating the schema and restoring is the
migration path.
"""
import json
from typing import Any, Generic, TypeVar

from sqlalchemy.engine import Engine as SqlAlchemyEngine
from sqlmodel import Session, SQLModel, create_engine, select

from config import Config
from core.observability import observed, LogPrefix

TableT = TypeVar("TableT", bound=SQLModel)


class Engine:
    """Builds and caches the SQLAlchemy engine — one per database URL, shared
    across every DB repository (its connection pool is reused, not duplicated)."""

    _engines: dict[str, SqlAlchemyEngine] = {}

    @staticmethod
    def get_engine(config: Config) -> SqlAlchemyEngine:
        """Return the engine for config.database_url, creating it once."""
        engine = Engine._engines.get(config.database_url)
        if engine is None:
            engine = Engine.create_db_engine(config)
            Engine._engines[config.database_url] = engine
        return engine

    @staticmethod
    @observed(LogPrefix.DB_ENGINE)
    def create_db_engine(config: Config) -> SqlAlchemyEngine:
        """Create the engine from config.database_url and ensure the schema."""
        engine = create_engine(
            config.database_url,
            echo=False,
            pool_pre_ping=True,
            json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
        )
        Engine._init_db(engine)
        return engine

    @staticmethod
    def _init_db(engine: SqlAlchemyEngine) -> None:
        """Create all tables if they do not exist."""
        SQLModel.metadata.create_all(engine)


class SqlRepository(Generic[TableT]):
    """Common plumbing: one Session per operation, plus CRUD by primary key.
    Concrete repositories add their own queries, reusing ``_session()`` for
    anything the base doesn't cover. Everything is in terms of ``*Table`` rows."""

    def __init__(self, config: Config, table: type[TableT]):
        self._engine = Engine.get_engine(config)
        self._table = table

    def _session(self) -> Session:
        """A new Session bound to the engine (one per operation). sqlmodel.Session
        is itself a context manager: use ``with self._session() as session:``."""
        return Session(self._engine)

    def get(self, pk: Any) -> TableT | None:
        """Row by primary key, or None if absent."""
        with self._session() as session:
            return session.get(self._table, pk)

    def list(self) -> list[TableT]:
        """Every row."""
        with self._session() as session:
            return list(session.exec(select(self._table)).all())

    def save(self, row: TableT) -> TableT:
        """Insert or update one row, returning the persisted row."""
        with self._session() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return row

    def delete(self, pk: Any) -> bool:
        """Remove one row by primary key. True if a row was deleted."""
        with self._session() as session:
            row = session.get(self._table, pk)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
