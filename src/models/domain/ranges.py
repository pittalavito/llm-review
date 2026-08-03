"""Single source of truth for the bounded numeric scales, and for deriving SQL
fragments (CHECK bounds, enum IN-tuples) from the project types.
"""

Range = tuple[int, int]
"""Inclusive integer bound as a ``(low, high)`` pair."""

RATING: Range = (1, 10)
"""Reviewer rating."""

CONFIDENCE: Range = (1, 5)
"""Reviewer / area-chair confidence."""

SCORE: Range = (1, 10)
"""Meta-review overall score."""


def sql_check_between(column: str, rng: Range, *, nullable: bool = True) -> str:
    """SQL boolean expression for a CHECK constraint bounding ``column`` to ``rng``.
    Nullable columns (the default) also allow NULL."""
    low, high = rng
    bounded = f"{column} BETWEEN {low} AND {high}"
    return f"{column} IS NULL OR {bounded}" if nullable else bounded