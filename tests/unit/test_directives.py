"""Tests for the directives system.

Directives modify how a Snippet is treated downstream — they can force
a classification, assert an expected error code, provide a fragment
wrap template, request a seed profile, or mark a snippet for elevated
execution. Directives arrive via two channels:

1. Leading ``-- @...`` comment lines inside the SQL body (inline).
2. A sidecar YAML file (``docs/sql-overrides.yaml``) keyed by snippet
   id or line number.

When both are present, inline wins.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from validator.directives import (
    DirectedSnippet,
    Directive,
    DirectiveParseError,
    DirectiveSet,
    apply_directives,
    load_sidecar,
    parse_inline,
)
from validator.models import Snippet


def _snip(sql: str, snippet_id: str = "sql-0001", line: int = 1) -> Snippet:
    return Snippet(id=snippet_id, line=line, section="Test", subsection=None, sql=sql)


# ───────── 1 — @skip directive ─────────


def test_inline_skip_directive_marks_snippet_skipped() -> None:
    sql = "-- @skip\nSELECT 1 FROM DUAL;"
    directives = parse_inline(_snip(sql))
    assert Directive.SKIP in directives


# ───────── 2 — @expect-error directive ─────────


def test_inline_expect_error_directive_records_expected_ora_code() -> None:
    sql = "-- @expect-error ORA-40569\nSELECT JSON_VALUE('{invalid');"
    directives = parse_inline(_snip(sql))
    assert directives.expected_error_code == "ORA-40569"


# ───────── 3 — @fragment directive forces classification ─────────


def test_inline_fragment_directive_forces_fragment_classification_even_for_select() -> None:
    sql = "-- @fragment\nSELECT * FROM orders;"
    directives = parse_inline(_snip(sql))
    assert Directive.FORCE_FRAGMENT in directives


# ───────── 4 — @wrap-as template ─────────


def test_inline_wrap_as_directive_overrides_default_wrap() -> None:
    sql = dedent(
        """\
        -- @wrap-as SELECT * FROM orders o WHERE %s
        JSON_EXISTS(o.order_doc, '$.items[*]')
        """
    )
    directives = parse_inline(_snip(sql))
    assert directives.wrap_as == "SELECT * FROM orders o WHERE %s"


# ───────── 5 — @requires-fixture directive ─────────


def test_inline_requires_fixture_directive_records_seed_profile() -> None:
    sql = "-- @requires-fixture tags-with-nums\nSELECT * FROM orders;"
    directives = parse_inline(_snip(sql))
    assert "tags-with-nums" in directives.required_fixtures


# ───────── 6 — @runs-as DBA directive ─────────


def test_inline_runs_as_dba_directive_records_elevated_execution() -> None:
    sql = "-- @runs-as DBA\nALTER SYSTEM FLUSH SHARED_POOL;"
    directives = parse_inline(_snip(sql))
    assert Directive.RUNS_AS_DBA in directives


# ───────── 7 — sidecar keyed by id ─────────


def test_sidecar_yaml_can_target_snippet_by_id(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text(
        dedent(
            """\
            overrides:
              sql-0012:
                - skip
            """
        )
    )
    overrides = load_sidecar(sidecar)
    assert Directive.SKIP in overrides["sql-0012"]


# ───────── 8 — sidecar keyed by line ─────────


def test_sidecar_yaml_can_target_snippet_by_line(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text(
        dedent(
            """\
            overrides:
              line:140:
                - expect-error: ORA-40596
            """
        )
    )
    overrides = load_sidecar(sidecar)
    assert overrides["line:140"].expected_error_code == "ORA-40596"


# ───────── 9 — inline wins over sidecar ─────────


def test_sidecar_overrides_merge_with_inline_directives_inline_wins(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text(
        dedent(
            """\
            overrides:
              sql-0001:
                - expect-error: ORA-99999
            """
        )
    )
    overrides = load_sidecar(sidecar)

    # Inline says ORA-40569; sidecar says ORA-99999. Inline wins.
    inline_sql = "-- @expect-error ORA-40569\nSELECT 1 FROM DUAL;"
    snippet = _snip(inline_sql, snippet_id="sql-0001")
    merged = apply_directives(snippet, overrides)
    assert merged.directives.expected_error_code == "ORA-40569"


# ───────── 10 — malformed directive raises ─────────


def test_malformed_directive_raises_directive_parse_error_with_line_reference() -> None:
    sql = "-- @expect-error\nSELECT 1 FROM DUAL;"  # missing ORA-NNNNN code
    with pytest.raises(DirectiveParseError) as excinfo:
        parse_inline(_snip(sql, line=42))
    message = str(excinfo.value)
    assert "line 42" in message or "sql-0001" in message


# ───────── Bonus: apply_directives produces DirectedSnippet ─────────


def test_apply_directives_returns_directed_snippet_with_empty_set_when_no_directives() -> None:
    """Sanity: a snippet with no directives and no sidecar entry should
    produce a ``DirectedSnippet`` with an empty :class:`DirectiveSet`.
    """
    snippet = _snip("SELECT 1 FROM DUAL;")
    directed = apply_directives(snippet, sidecar_overrides={})
    assert isinstance(directed, DirectedSnippet)
    assert isinstance(directed.directives, DirectiveSet)
    assert not list(directed.directives)
