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


# ───────── Edge cases — inline parsing ─────────


def test_inline_parser_tolerates_leading_blank_lines_and_plain_comments() -> None:
    """A regular `--` comment with no `@directive` is allowed in the
    leading comment block and silently ignored. Blank lines are
    tolerated too. The parser only breaks on the first *real* SQL line.
    """
    sql = "\n-- regular comment not a directive\n-- @skip\nSELECT 1 FROM DUAL;"
    directives = parse_inline(_snip(sql))
    assert Directive.SKIP in directives


def test_inline_runs_as_rejects_non_dba_payload() -> None:
    sql = "-- @runs-as superuser\nSELECT 1 FROM DUAL;"
    with pytest.raises(DirectiveParseError, match="@runs-as expects 'DBA'"):
        parse_inline(_snip(sql))


def test_inline_wrap_as_rejects_empty_payload() -> None:
    sql = "-- @wrap-as\nJSON_EXISTS(doc, '$.x')"
    with pytest.raises(DirectiveParseError, match="@wrap-as requires a template"):
        parse_inline(_snip(sql))


def test_inline_requires_fixture_rejects_empty_payload() -> None:
    sql = "-- @requires-fixture\nSELECT 1 FROM DUAL;"
    with pytest.raises(DirectiveParseError, match="@requires-fixture requires a profile name"):
        parse_inline(_snip(sql))


def test_inline_unknown_directive_raises() -> None:
    sql = "-- @whoops-unknown\nSELECT 1 FROM DUAL;"
    with pytest.raises(DirectiveParseError, match="unknown directive"):
        parse_inline(_snip(sql))


# ───────── Edge cases — sidecar loader ─────────


def test_load_sidecar_returns_empty_dict_when_file_does_not_exist(tmp_path: Path) -> None:
    assert load_sidecar(tmp_path / "does-not-exist.yaml") == {}


def test_load_sidecar_handles_empty_yaml(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("")
    assert load_sidecar(sidecar) == {}


def test_sidecar_accepts_fragment_bare_directive(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - fragment\n")
    overrides = load_sidecar(sidecar)
    assert Directive.FORCE_FRAGMENT in overrides["sql-0001"]


def test_sidecar_accepts_wrap_as_payload(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - wrap-as: SELECT * FROM orders o WHERE %s\n")
    overrides = load_sidecar(sidecar)
    assert overrides["sql-0001"].wrap_as == "SELECT * FROM orders o WHERE %s"


def test_sidecar_accepts_requires_fixture_payload(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - requires-fixture: deep-nest\n")
    overrides = load_sidecar(sidecar)
    assert "deep-nest" in overrides["sql-0001"].required_fixtures


def test_sidecar_accepts_runs_as_dba(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - runs-as: DBA\n")
    overrides = load_sidecar(sidecar)
    assert Directive.RUNS_AS_DBA in overrides["sql-0001"]


def test_sidecar_rejects_unknown_bare_directive(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - whoops\n")
    with pytest.raises(DirectiveParseError, match="unknown bare directive"):
        load_sidecar(sidecar)


def test_sidecar_rejects_unknown_keyed_directive(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - mystery: 42\n")
    with pytest.raises(DirectiveParseError, match="unknown directive"):
        load_sidecar(sidecar)


def test_sidecar_rejects_invalid_ora_code(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - expect-error: not-an-ora-code\n")
    with pytest.raises(DirectiveParseError, match="expect-error expects"):
        load_sidecar(sidecar)


def test_sidecar_rejects_runs_as_non_dba(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - runs-as: guest\n")
    with pytest.raises(DirectiveParseError, match="runs-as expects 'DBA'"):
        load_sidecar(sidecar)


def test_sidecar_rejects_empty_wrap_as_payload(tmp_path: Path) -> None:
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - wrap-as: ''\n")
    with pytest.raises(DirectiveParseError, match="wrap-as requires a template"):
        load_sidecar(sidecar)


def test_sidecar_rejects_malformed_entry(tmp_path: Path) -> None:
    """A list entry that's neither a string nor a single-key mapping is malformed."""
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  sql-0001:\n    - [a, b, c]\n")
    with pytest.raises(DirectiveParseError, match="malformed entry"):
        load_sidecar(sidecar)


# ───────── Apply wiring ─────────


def test_apply_directives_pulls_by_line_key(tmp_path: Path) -> None:
    """A sidecar keyed by ``line:<n>`` applies to a snippet at that line."""
    sidecar = tmp_path / "overrides.yaml"
    sidecar.write_text("overrides:\n  line:42:\n    - skip\n")
    overrides = load_sidecar(sidecar)

    snippet = _snip("SELECT 1 FROM DUAL;", line=42)
    directed = apply_directives(snippet, overrides)
    assert Directive.SKIP in directed.directives
