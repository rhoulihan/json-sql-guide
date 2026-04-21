"""Classify each extracted Snippet as standalone, fragment, or comment-only.

The classifier is a pure function. It does not execute SQL, touch a
database, or look at directives (directives are a separate concern that
may override classification downstream).

Classification rules (applied in order, first match wins)
---------------------------------------------------------

1. Strip every leading ``--`` comment line. If nothing remains, the
   snippet is :attr:`Classification.COMMENT_ONLY`.
2. Inspect the first non-comment token (case-insensitive):

   * ``SELECT``, ``WITH``, ``INSERT``, ``UPDATE``, ``DELETE``, ``MERGE``
     → :attr:`Classification.STANDALONE_QUERY`
   * ``CREATE``, ``ALTER``, ``DROP``
     → :attr:`Classification.STANDALONE_DDL`
   * ``WHERE``, ``JSON_TABLE``, ``NESTED``, ``CYCLE``
     → :attr:`Classification.FRAGMENT`
3. Anything else falls through to ``FRAGMENT`` with ``rationale`` noting
   the unrecognized prefix. Callers can override with an ``@fragment``
   directive when appropriate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from validator.models import Snippet

__all__ = ["Classification", "ClassifiedSnippet", "classify"]


class Classification(Enum):
    """Outcome of classifying one snippet."""

    STANDALONE_QUERY = "standalone_query"
    STANDALONE_DDL = "standalone_ddl"
    FRAGMENT = "fragment"
    COMMENT_ONLY = "comment_only"


@dataclass(frozen=True, slots=True)
class ClassifiedSnippet:
    """A Snippet paired with its classification and a short rationale."""

    snippet: Snippet
    classification: Classification
    rationale: str


# ───────── First-token rules ─────────

_QUERY_STARTERS = frozenset({"SELECT", "WITH", "INSERT", "UPDATE", "DELETE", "MERGE"})
_DDL_STARTERS = frozenset({"CREATE", "ALTER", "DROP"})
_FRAGMENT_STARTERS = frozenset({"WHERE", "JSON_TABLE", "NESTED", "CYCLE"})

_COMMENT_LINE = re.compile(r"^\s*--.*$")
_BLANK_LINE = re.compile(r"^\s*$")
_FIRST_TOKEN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)")


def classify(snippet: Snippet) -> ClassifiedSnippet:
    """Return a :class:`ClassifiedSnippet` for *snippet*."""
    body = _strip_leading_comments(snippet.sql)

    if not body.strip():
        return ClassifiedSnippet(
            snippet=snippet,
            classification=Classification.COMMENT_ONLY,
            rationale="body contains only comments or whitespace",
        )

    match = _FIRST_TOKEN.match(body)
    if match is None:
        return ClassifiedSnippet(
            snippet=snippet,
            classification=Classification.FRAGMENT,
            rationale="no identifier at start of body",
        )

    token = match.group(1).upper()

    if token in _QUERY_STARTERS:
        return ClassifiedSnippet(
            snippet=snippet,
            classification=Classification.STANDALONE_QUERY,
            rationale=f"first token is {token!r}",
        )

    if token in _DDL_STARTERS:
        return ClassifiedSnippet(
            snippet=snippet,
            classification=Classification.STANDALONE_DDL,
            rationale=f"first token is {token!r}",
        )

    if token in _FRAGMENT_STARTERS:
        return ClassifiedSnippet(
            snippet=snippet,
            classification=Classification.FRAGMENT,
            rationale=f"first token is {token!r} — partial expression",
        )

    return ClassifiedSnippet(
        snippet=snippet,
        classification=Classification.FRAGMENT,
        rationale=f"unrecognized first token {token!r} — treating as fragment",
    )


def _strip_leading_comments(sql: str) -> str:
    """Remove leading ``--`` and blank lines; return the rest unchanged."""
    lines = sql.splitlines()
    first_meaningful = 0
    for i, line in enumerate(lines):
        if _COMMENT_LINE.match(line) or _BLANK_LINE.match(line):
            continue
        first_meaningful = i
        break
    else:
        # All lines were comments or blanks.
        return ""

    return "\n".join(lines[first_meaningful:])
