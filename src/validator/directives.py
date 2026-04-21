"""Directive parsing — inline comments and sidecar YAML.

Directives modify how the runner treats a Snippet. They arrive two ways:

1. **Inline** — leading ``-- @...`` comment lines at the top of the SQL
   body. Only lines *before* the first non-comment/non-blank line count.
2. **Sidecar** — ``docs/sql-overrides.yaml`` keyed by snippet ``id``
   (e.g. ``sql-0012``) or ``line:<n>``.

When both sources yield directives for the same snippet, **inline wins**
per-field: an inline ``@expect-error ORA-40569`` beats a sidecar
``expect-error: ORA-99999`` for the same snippet.

Supported directives (case-insensitive keyword after ``@``):

* ``@skip`` — runner should skip this snippet entirely.
* ``@fragment`` — force classifier to treat this as a fragment, even
  if it would otherwise be classified standalone.
* ``@expect-error ORA-NNNNN`` — assert a specific Oracle error code.
* ``@wrap-as <template>`` — override the default fragment wrap; the
  template's ``%s`` is replaced with the snippet body.
* ``@requires-fixture <name>`` — request a named seed profile before
  the snippet runs.
* ``@runs-as DBA`` — execute under the elevated DBA connection.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from validator.models import Snippet

__all__ = [
    "DirectedSnippet",
    "Directive",
    "DirectiveParseError",
    "DirectiveSet",
    "apply_directives",
    "load_sidecar",
    "parse_inline",
]


class Directive(Enum):
    """Discrete directive flags."""

    SKIP = "skip"
    FORCE_FRAGMENT = "fragment"
    RUNS_AS_DBA = "runs_as_dba"


class DirectiveParseError(ValueError):
    """Raised when an inline directive is malformed."""


@dataclass(frozen=True, slots=True)
class DirectiveSet:
    """Bundle of directives applying to one snippet.

    ``flags`` holds boolean-style directives (SKIP, FORCE_FRAGMENT,
    RUNS_AS_DBA). ``expected_error_code``, ``wrap_as``, and
    ``required_fixtures`` hold payload directives.
    """

    flags: frozenset[Directive] = field(default_factory=frozenset)
    expected_error_code: str | None = None
    wrap_as: str | None = None
    required_fixtures: frozenset[str] = field(default_factory=frozenset)

    def __contains__(self, directive: Directive) -> bool:
        return directive in self.flags

    def __iter__(self) -> Iterator[Directive]:
        return iter(self.flags)

    def merge(self, lower_priority: DirectiveSet) -> DirectiveSet:
        """Return a new set where *self* wins on overlapping fields.

        Used to merge inline (self) with sidecar (lower_priority).
        """
        return DirectiveSet(
            flags=self.flags | lower_priority.flags,
            expected_error_code=self.expected_error_code or lower_priority.expected_error_code,
            wrap_as=self.wrap_as or lower_priority.wrap_as,
            required_fixtures=self.required_fixtures | lower_priority.required_fixtures,
        )


@dataclass(frozen=True, slots=True)
class DirectedSnippet:
    """A Snippet augmented with its resolved directives."""

    snippet: Snippet
    directives: DirectiveSet


# ───────── Inline parsing ─────────

_ORA_CODE = re.compile(r"ORA-\d{4,5}")
_DIRECTIVE_LINE = re.compile(r"^\s*--\s*@([a-z-]+)(?:\s+(.*))?\s*$", re.IGNORECASE)
_COMMENT_LINE = re.compile(r"^\s*--.*$")
_BLANK_LINE = re.compile(r"^\s*$")


def parse_inline(snippet: Snippet) -> DirectiveSet:
    """Parse ``-- @...`` directives from the top of *snippet.sql*.

    Only leading ``--`` lines are scanned. The first non-comment,
    non-blank line terminates the header.
    """
    flags: set[Directive] = set()
    expected_error: str | None = None
    wrap_as: str | None = None
    fixtures: set[str] = set()

    for raw_line in snippet.sql.splitlines():
        if _BLANK_LINE.match(raw_line):
            continue
        if not _COMMENT_LINE.match(raw_line):
            break  # First non-comment line ends the header.

        match = _DIRECTIVE_LINE.match(raw_line)
        if match is None:
            # A plain comment (no @directive) is allowed before directives.
            continue

        name = match.group(1).lower()
        payload = (match.group(2) or "").strip()

        if name == "skip":
            flags.add(Directive.SKIP)
        elif name == "fragment":
            flags.add(Directive.FORCE_FRAGMENT)
        elif name == "runs-as":
            if payload.upper() == "DBA":
                flags.add(Directive.RUNS_AS_DBA)
            else:
                raise DirectiveParseError(
                    f"@runs-as expects 'DBA' (got {payload!r}) at {snippet.id} line {snippet.line}"
                )
        elif name == "expect-error":
            if not _ORA_CODE.fullmatch(payload):
                raise DirectiveParseError(
                    f"@expect-error expects an 'ORA-NNNNN' code (got {payload!r}) "
                    f"at {snippet.id} line {snippet.line}"
                )
            expected_error = payload
        elif name == "wrap-as":
            if not payload:
                raise DirectiveParseError(
                    f"@wrap-as requires a template string at {snippet.id} line {snippet.line}"
                )
            wrap_as = payload
        elif name == "requires-fixture":
            if not payload:
                raise DirectiveParseError(
                    f"@requires-fixture requires a profile name at {snippet.id} line {snippet.line}"
                )
            fixtures.add(payload)
        else:
            raise DirectiveParseError(
                f"unknown directive '@{name}' at {snippet.id} line {snippet.line}"
            )

    return DirectiveSet(
        flags=frozenset(flags),
        expected_error_code=expected_error,
        wrap_as=wrap_as,
        required_fixtures=frozenset(fixtures),
    )


# ───────── Sidecar parsing ─────────


def load_sidecar(path: Path) -> dict[str, DirectiveSet]:
    """Load ``docs/sql-overrides.yaml``.

    Schema::

        overrides:
          sql-0012:
            - skip
          line:140:
            - expect-error: ORA-40596
          sql-0005:
            - fragment
            - requires-fixture: tags-with-nums

    Returns a mapping from key (``sql-NNNN`` or ``line:N``) to a
    :class:`DirectiveSet`.
    """
    if not path.exists():
        return {}

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    overrides_section: dict[str, list[Any]] = raw.get("overrides") or {}

    out: dict[str, DirectiveSet] = {}
    for key, entries in overrides_section.items():
        out[str(key)] = _build_directive_set(entries, where=f"sidecar:{key}")
    return out


def _build_directive_set(entries: list[Any], *, where: str) -> DirectiveSet:
    flags: set[Directive] = set()
    expected_error: str | None = None
    wrap_as: str | None = None
    fixtures: set[str] = set()

    for entry in entries:
        if isinstance(entry, str):
            name = entry.lower()
            if name == "skip":
                flags.add(Directive.SKIP)
            elif name == "fragment":
                flags.add(Directive.FORCE_FRAGMENT)
            else:
                raise DirectiveParseError(f"unknown bare directive {entry!r} in {where}")
        elif isinstance(entry, dict) and len(entry) == 1:
            ((raw_name, payload_any),) = entry.items()
            name = str(raw_name).lower()
            payload = str(payload_any) if payload_any is not None else ""
            if name == "expect-error":
                if not _ORA_CODE.fullmatch(payload):
                    raise DirectiveParseError(
                        f"expect-error expects 'ORA-NNNNN' (got {payload!r}) in {where}"
                    )
                expected_error = payload
            elif name == "wrap-as":
                if not payload:
                    raise DirectiveParseError(f"wrap-as requires a template in {where}")
                wrap_as = payload
            elif name == "requires-fixture":
                fixtures.add(payload)
            elif name == "runs-as":
                if payload.upper() == "DBA":
                    flags.add(Directive.RUNS_AS_DBA)
                else:
                    raise DirectiveParseError(f"runs-as expects 'DBA' in {where} (got {payload!r})")
            else:
                raise DirectiveParseError(f"unknown directive {name!r} in {where}")
        else:
            raise DirectiveParseError(f"malformed entry {entry!r} in {where}")

    return DirectiveSet(
        flags=frozenset(flags),
        expected_error_code=expected_error,
        wrap_as=wrap_as,
        required_fixtures=frozenset(fixtures),
    )


# ───────── Apply (inline + sidecar, inline wins) ─────────


def apply_directives(
    snippet: Snippet,
    sidecar_overrides: dict[str, DirectiveSet],
) -> DirectedSnippet:
    """Resolve a snippet's effective directives.

    Inline directives win on overlapping fields. A sidecar entry keyed
    by either ``snippet.id`` or ``line:<line>`` contributes.
    """
    inline = parse_inline(snippet)

    sidecar = DirectiveSet()
    for key in (snippet.id, f"line:{snippet.line}"):
        if key in sidecar_overrides:
            sidecar = sidecar.merge(sidecar_overrides[key])

    effective = inline.merge(sidecar)
    return DirectedSnippet(snippet=replace(snippet), directives=effective)
