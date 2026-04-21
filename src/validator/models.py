"""Core data types for the validator.

These dataclasses are the shared vocabulary between extractor, classifier,
directives, wraps, runner, and reporter. Keep them small, frozen, and with
no behavior — behavior lives in the modules that produce or consume them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Snippet:
    """One fenced ```sql block from the guide.

    Produced by the extractor. Uniquely identified by ``id`` (sequential,
    zero-padded per appearance order: ``sql-0001``, ``sql-0002``, …).
    """

    id: str
    line: int
    section: str
    subsection: str | None
    sql: str

    def to_dict(self) -> dict[str, Any]:
        """Render as JSON-safe dict for catalog serialization."""
        return asdict(self)
