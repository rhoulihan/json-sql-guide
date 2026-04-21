"""Markdown → SQL snippet catalog.

Pure parser. No classification, no execution. Walks the text once,
tracking current section (H2) and subsection (H3), toggling an "inside
fence" state when it sees ``` ```sql ```, and appending a ``Snippet`` on
the matching close.

Design notes
------------
* Only ``` ```sql ``` fences count. ``` ```json ```, ``` ```python ```,
  and un-tagged ``` ``` ``` fences are skipped entirely.
* A new H2 heading resets the current subsection back to ``None`` — the
  subsection only applies while we're inside its parent H2.
* Snippet ids are assigned by appearance order (``sql-0001`` onward).
* Line numbers refer to the opening fence line, 1-indexed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from validator.models import Snippet

__all__ = ["Snippet", "UnclosedFenceError", "extract", "extract_file"]


# ───────── Errors ─────────


class UnclosedFenceError(ValueError):
    """Raised when a ``` ```sql ``` fence is opened but never closed.

    The message references the opening line so contributors can find it fast.
    """


# ───────── Internal parser state ─────────


_SQL_FENCE_OPEN = re.compile(r"^```sql\s*$")
_FENCE_CLOSE = re.compile(r"^```\s*$")
_ANY_FENCE_OPEN = re.compile(r"^```[^\s]*\s*$")  # non-sql opener we skip
_H2 = re.compile(r"^##\s+(.+?)\s*$")
_H3 = re.compile(r"^###\s+(.+?)\s*$")


@dataclass
class _State:
    """Single-pass parser state. Private — callers use ``extract()``."""

    section: str = ""
    subsection: str | None = None
    inside_sql: bool = False
    inside_other: bool = False
    sql_open_line: int = 0
    buffer: list[str] = field(default_factory=list)
    snippets: list[Snippet] = field(default_factory=list)


# ───────── Public API ─────────


def extract(text: str) -> list[Snippet]:
    """Extract every ``` ```sql ``` block from *text*.

    Returns a list of ``Snippet`` records in document order. Empty list if
    the document has no fenced SQL. Raises ``UnclosedFenceError`` if a
    ``` ```sql ``` opener has no matching closer.
    """
    state = _State()
    for line_num, raw_line in enumerate(text.splitlines(), start=1):
        _handle_line(state, raw_line, line_num)

    if state.inside_sql:
        raise UnclosedFenceError(
            f"``` ```sql ``` opened at line {state.sql_open_line} was never closed "
            f"(line={state.sql_open_line})"
        )

    return state.snippets


def extract_file(path: Path) -> list[Snippet]:
    """Thin I/O wrapper over :func:`extract`."""
    return extract(Path(path).read_text(encoding="utf-8"))


# ───────── Line-level dispatcher ─────────


def _handle_line(state: _State, line: str, line_num: int) -> None:
    """Dispatch one line against the parser state.

    Order of checks matters:

    1. If inside a ``sql`` block, only a closing fence or body text.
    2. If inside a non-sql block, only a closing fence is meaningful.
    3. Otherwise, it's a structural line (heading or fence opener) or prose.
    """
    if state.inside_sql:
        if _FENCE_CLOSE.match(line):
            _finalize_sql_block(state)
        else:
            state.buffer.append(line)
        return

    if state.inside_other:
        if _FENCE_CLOSE.match(line):
            state.inside_other = False
        return

    if _SQL_FENCE_OPEN.match(line):
        state.inside_sql = True
        state.sql_open_line = line_num
        state.buffer = []
        return

    if _ANY_FENCE_OPEN.match(line):
        state.inside_other = True
        return

    if (m := _H2.match(line)) is not None:
        state.section = m.group(1)
        state.subsection = None
        return

    if (m := _H3.match(line)) is not None:
        state.subsection = m.group(1)
        return


def _finalize_sql_block(state: _State) -> None:
    """Emit the current buffer as a ``Snippet`` and reset fence state."""
    snippet = Snippet(
        id=f"sql-{len(state.snippets) + 1:04d}",
        line=state.sql_open_line,
        section=state.section,
        subsection=state.subsection,
        sql="\n".join(state.buffer),
    )
    state.snippets.append(snippet)
    state.inside_sql = False
    state.buffer = []
    state.sql_open_line = 0
