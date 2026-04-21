"""Tests for the fragment wrap registry.

Fragments are partial SQL expressions that won't execute as-is — things
like a bare ``WHERE`` clause, a standalone ``JSON_TABLE`` expression,
a ``NESTED PATH`` sub-clause, or a ``CYCLE`` clause. The wrap registry
maps each shape to a template that produces an executable statement.

The ``wrap()`` function accepts a ``DirectedSnippet`` (so an explicit
``@wrap-as`` directive wins over registry defaults) and returns a
``WrappedSnippet`` carrying the original plus the final executable SQL.
"""

from __future__ import annotations

import pytest

from validator.directives import DirectedSnippet, DirectiveSet
from validator.models import Snippet
from validator.wraps import (
    FragmentShape,
    UnwrappableFragmentError,
    WrappedSnippet,
    register,
    wrap,
)


def _directed(sql: str, wrap_as: str | None = None) -> DirectedSnippet:
    snippet = Snippet(id="sql-0001", line=1, section="T", subsection=None, sql=sql)
    return DirectedSnippet(
        snippet=snippet,
        directives=DirectiveSet(wrap_as=wrap_as),
    )


# ───────── 1 — WHERE fragment has a registered wrap ─────────


def test_wrap_registry_has_entry_for_where_json_exists_fragment() -> None:
    directed = _directed("WHERE JSON_EXISTS(o.order_doc, '$.items[*]')")
    wrapped = wrap(directed)
    assert isinstance(wrapped, WrappedSnippet)
    assert "SELECT" in wrapped.executable_sql.upper()
    assert "WHERE JSON_EXISTS" in wrapped.executable_sql


# ───────── 2 — registry applies template substitution ─────────


def test_wrap_registry_applies_template_to_produce_executable_sql() -> None:
    directed = _directed("WHERE o.order_id > 100")
    wrapped = wrap(directed)
    assert "WHERE o.order_id > 100" in wrapped.executable_sql
    # The wrapped SQL should be syntactically executable (starts with SELECT/INSERT/etc).
    first_token = wrapped.executable_sql.strip().split()[0].upper()
    assert first_token == "SELECT"


# ───────── 3 — @wrap-as directive beats registry default ─────────


def test_wrap_registry_falls_through_to_explicit_wrap_as_directive_when_provided() -> None:
    directed = _directed(
        "JSON_EXISTS(o.order_doc, '$.x')",
        wrap_as="SELECT 1 FROM orders o WHERE %s",
    )
    wrapped = wrap(directed)
    assert wrapped.executable_sql == "SELECT 1 FROM orders o WHERE JSON_EXISTS(o.order_doc, '$.x')"
    assert wrapped.shape is FragmentShape.DIRECTIVE_OVERRIDE


# ───────── 4 — JSON_TABLE fragment wraps in cross join ─────────


def test_wrap_registry_for_json_table_expression_wraps_in_cross_join() -> None:
    sql = "JSON_TABLE(o.order_doc, '$.items[*]' COLUMNS (sku VARCHAR2(50) PATH '$.sku'))"
    directed = _directed(sql)
    wrapped = wrap(directed)
    assert "JSON_TABLE" in wrapped.executable_sql
    upper = wrapped.executable_sql.upper()
    # A cross join with orders is the default wrap — either written as a
    # comma or as CROSS JOIN.
    assert "FROM ORDERS" in upper or "FROM ORDERS O," in upper
    assert "FETCH FIRST" in upper


# ───────── 5 — NESTED PATH fragment injected into minimal parent ─────────


def test_wrap_registry_for_nested_path_fragment_injects_into_minimal_json_table_parent() -> None:
    directed = _directed("NESTED PATH '$.items[*]' COLUMNS (sku VARCHAR2(50) PATH '$.sku')")
    wrapped = wrap(directed)
    upper = wrapped.executable_sql.upper()
    assert "JSON_TABLE" in upper
    assert "NESTED PATH" in upper
    assert "COLUMNS" in upper


# ───────── 6 — CYCLE clause injected into minimal recursive CTE ─────────


def test_wrap_registry_for_cycle_clause_fragment_injects_into_minimal_recursive_cte() -> None:
    directed = _directed("CYCLE id SET is_cycle TO 'Y' DEFAULT 'N'")
    wrapped = wrap(directed)
    upper = wrapped.executable_sql.upper()
    assert "WITH" in upper
    assert "CYCLE" in upper
    assert "IS_CYCLE" in upper


# ───────── 7 — unrecognized shape raises ─────────


def test_wrap_registry_raises_when_fragment_shape_not_recognized() -> None:
    directed = _directed("???completely unrecognizable garbage???")
    with pytest.raises(UnwrappableFragmentError):
        wrap(directed)


# ───────── 8 — register() extension point ─────────


def test_wrap_registry_is_extensible_via_register_wrapper_function() -> None:
    """register() adds a new shape matcher + template to the registry."""
    # Use a sentinel marker unlikely to collide with the defaults.
    marker = "ZZZMARKER"

    @register(
        FragmentShape.CUSTOM,
        matcher=lambda body: body.strip().startswith(marker),
        template=f"SELECT 1 FROM DUAL WHERE '%s' LIKE '{marker}%%'",
    )
    def _custom_wrapper() -> None:  # pragma: no cover — registration side-effect
        """Anchor for documentation; behavior lives in matcher+template."""

    try:
        directed = _directed(f"{marker} some body")
        wrapped = wrap(directed)
        assert marker in wrapped.executable_sql
        assert wrapped.shape is FragmentShape.CUSTOM
    finally:
        # Clean up so later tests don't see the custom shape.
        from validator.wraps import _unregister  # type: ignore[attr-defined]

        _unregister(FragmentShape.CUSTOM)


# ───────── 9 — wrapped SQL is syntactically parseable ─────────


def test_wrapped_sql_parses_as_valid_oracle_sql_no_execution() -> None:
    """Local sanity check — no real parser, just that the wrapped SQL
    starts with an allowed top-level keyword and contains no obvious
    template-substitution artifacts like `%s` leftover.
    """
    for fragment in (
        "WHERE o.x > 1",
        "JSON_TABLE(o.d, '$' COLUMNS (x NUMBER PATH '$.x'))",
        "NESTED PATH '$.a' COLUMNS (x NUMBER PATH '$.x')",
        "CYCLE id SET flag TO 'Y' DEFAULT 'N'",
    ):
        directed = _directed(fragment)
        wrapped = wrap(directed)
        first_token = wrapped.executable_sql.strip().split()[0].upper()
        assert first_token in {"SELECT", "WITH"}, fragment
        assert "%s" not in wrapped.executable_sql, fragment


# ───────── 10 — diagnostic comment for debuggability ─────────


def test_wrap_registry_emits_diagnostic_comment_in_wrapped_sql_for_debuggability() -> None:
    """The wrapped SQL should include a leading `-- wrapped from sql-NNNN`
    comment so log output points back to the source snippet.
    """
    directed = _directed("WHERE o.x = 1")
    wrapped = wrap(directed)
    first_line = wrapped.executable_sql.splitlines()[0]
    assert first_line.startswith("-- wrapped")
    assert "sql-0001" in first_line
