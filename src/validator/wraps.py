"""Fragment wrap registry — turn partial SQL into executable SQL.

A *fragment* is an SQL expression that won't parse as a top-level
statement: a bare ``WHERE`` clause, a standalone ``JSON_TABLE``
expression, a ``NESTED PATH`` sub-clause, or a ``CYCLE`` clause from a
recursive CTE. This module owns the mapping from fragment shape to
executable template.

Priority order when wrapping a snippet:

1. **Directive override** — if the snippet carries an ``@wrap-as``
   directive, its template wins. This is the escape hatch for snippets
   that don't match any built-in shape.
2. **Registered shape matcher** — the first registered ``FragmentShape``
   whose matcher returns ``True`` for the fragment body wins.
3. **Unwrappable** — nothing matched; raise
   :class:`UnwrappableFragmentError`.

Templates use ``%s`` as the single substitution slot for the fragment
body. Every wrapped SQL gets a leading ``-- wrapped from <id>`` comment
for traceability in logs and annotated reports.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from validator.directives import DirectedSnippet

__all__ = [
    "FragmentShape",
    "UnwrappableFragmentError",
    "WrappedSnippet",
    "register",
    "wrap",
]


class FragmentShape(Enum):
    """Built-in shapes recognized by the registry."""

    DIRECTIVE_OVERRIDE = "directive_override"
    WHERE = "where"
    JSON_TABLE = "json_table"
    NESTED_PATH = "nested_path"
    CYCLE = "cycle"
    CUSTOM = "custom"  # reserved for test/extension usage


class UnwrappableFragmentError(ValueError):
    """Raised when no registered shape matches a fragment body."""


@dataclass(frozen=True, slots=True)
class WrappedSnippet:
    """A fragment augmented with its executable SQL and matched shape."""

    directed: DirectedSnippet
    executable_sql: str
    shape: FragmentShape


# ───────── Registry ─────────

Matcher = Callable[[str], bool]


@dataclass(slots=True)
class _Entry:
    shape: FragmentShape
    matcher: Matcher
    template: str


_REGISTRY: list[_Entry] = []


def register(
    shape: FragmentShape,
    *,
    matcher: Matcher,
    template: str,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Register a wrap for *shape*.

    Used as a decorator (the decorated function is ignored — only the
    side-effect of registering the matcher + template matters). Can also
    be called directly.
    """
    entry = _Entry(shape=shape, matcher=matcher, template=template)
    _REGISTRY.append(entry)

    def _decorator(fn: Callable[..., object]) -> Callable[..., object]:
        return fn

    return _decorator


def _unregister(shape: FragmentShape) -> None:
    """Remove all registered entries for *shape*. Intended for tests."""
    global _REGISTRY
    _REGISTRY = [e for e in _REGISTRY if e.shape is not shape]


# ───────── Built-in shape matchers ─────────


def _strip_leading_comments(body: str) -> str:
    lines: list[str] = []
    skipping = True
    for line in body.splitlines():
        if skipping and (line.strip().startswith("--") or line.strip() == ""):
            continue
        skipping = False
        lines.append(line)
    return "\n".join(lines).strip()


def _matches_keyword(keyword: str) -> Matcher:
    pattern = re.compile(rf"^\s*{keyword}\b", re.IGNORECASE)

    def _m(body: str) -> bool:
        return bool(pattern.match(_strip_leading_comments(body)))

    return _m


register(
    FragmentShape.WHERE,
    matcher=_matches_keyword("WHERE"),
    template="SELECT 1 FROM orders o %s FETCH FIRST 1 ROW ONLY",
)

register(
    FragmentShape.JSON_TABLE,
    matcher=_matches_keyword("JSON_TABLE"),
    template=("SELECT t.* FROM orders o, %s t FETCH FIRST 1 ROW ONLY"),
)

register(
    FragmentShape.NESTED_PATH,
    matcher=_matches_keyword("NESTED"),
    template=(
        "SELECT t.* FROM orders o,\n"
        "JSON_TABLE(o.order_doc, '$'\n"
        "  COLUMNS (\n"
        "    %s\n"
        "  )) t\n"
        "FETCH FIRST 1 ROW ONLY"
    ),
)

register(
    FragmentShape.CYCLE,
    matcher=_matches_keyword("CYCLE"),
    template=(
        "WITH r (id, parent_id) AS (\n"
        "  SELECT 1 AS id, NULL AS parent_id FROM DUAL\n"
        "  UNION ALL\n"
        "  SELECT r.id + 1, r.id FROM r WHERE r.id < 3\n"
        ") %s\n"
        "SELECT * FROM r"
    ),
)


# ───────── Public entrypoint ─────────


def wrap(directed: DirectedSnippet) -> WrappedSnippet:
    """Return a :class:`WrappedSnippet` for *directed*."""
    body = _strip_leading_comments(directed.snippet.sql)

    if directed.directives.wrap_as is not None:
        executable = directed.directives.wrap_as % body
        return WrappedSnippet(
            directed=directed,
            executable_sql=_with_diagnostic(directed, executable),
            shape=FragmentShape.DIRECTIVE_OVERRIDE,
        )

    for entry in _REGISTRY:
        if entry.matcher(body):
            executable = entry.template % body
            return WrappedSnippet(
                directed=directed,
                executable_sql=_with_diagnostic(directed, executable),
                shape=entry.shape,
            )

    raise UnwrappableFragmentError(
        f"no wrap registered for fragment {directed.snippet.id} "
        f"(line {directed.snippet.line}): {body[:60]!r}"
    )


def _with_diagnostic(directed: DirectedSnippet, sql: str) -> str:
    """Prefix the executable SQL with a `-- wrapped from <id>` comment."""
    return (
        f"-- wrapped from {directed.snippet.id} "
        f"(line {directed.snippet.line}, section {directed.snippet.section!r})\n"
        f"{sql}"
    )
