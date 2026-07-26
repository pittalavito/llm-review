"""Single source of truth for the bounded numeric scales, and for deriving SQL
fragments (CHECK bounds, enum IN-tuples) from the project types.
"""
from enum import Enum

from pydantic import Field
from pydantic.fields import FieldInfo

Range = tuple[int, int]
"""Inclusive integer bound as a ``(low, high)`` pair."""

RATING: Range = (1, 10)
"""Reviewer rating."""

CONFIDENCE: Range = (1, 5)
"""Reviewer / area-chair confidence."""

SCORE: Range = (1, 10)
"""Meta-review overall score."""


def field(rng: Range, **kwargs) -> FieldInfo:
    """A Pydantic ``Field`` bounded (inclusive) to ``rng``, plus extra kwargs."""
    return Field(ge=rng[0], le=rng[1], **kwargs)


def sql_check_between(column: str, rng: Range, *, nullable: bool = True) -> str:
    """SQL boolean expression for a CHECK constraint bounding ``column`` to ``rng``.
    Nullable columns (the default) also allow NULL."""
    low, high = rng
    bounded = f"{column} BETWEEN {low} AND {high}"
    return f"{column} IS NULL OR {bounded}" if nullable else bounded


def sql_in(enum_cls: type[Enum]) -> str:
    """SQL tuple literal of an enum's values, e.g. ``('a','b')`` — for ``col IN (...)``."""
    return "(" + ",".join(f"'{member.value}'" for member in enum_cls) + ")"
