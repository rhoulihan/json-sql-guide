"""Tests for the SQL snippet classifier.

Given a Snippet, the classifier assigns one of four categories:
  - standalone_query   (SELECT, WITH, INSERT, UPDATE, DELETE, MERGE)
  - standalone_ddl     (CREATE, ALTER, DROP, plus JSON RELATIONAL DUALITY VIEW)
  - fragment           (partial expressions: WHERE, JSON_TABLE, NESTED PATH, CYCLE)
  - comment_only       (body is nothing but -- lines)

The classifier is a pure function over Snippet. No I/O, no DB.
"""

from __future__ import annotations

from validator.classifier import Classification, ClassifiedSnippet, classify
from validator.models import Snippet


def _snip(sql: str, snippet_id: str = "sql-0001") -> Snippet:
    """Shorthand: build a Snippet around a raw SQL body."""
    return Snippet(id=snippet_id, line=1, section="Test", subsection=None, sql=sql)


# ───────── 1 — SELECT → standalone_query ─────────


def test_classifier_tags_select_as_standalone_query() -> None:
    result = classify(_snip("SELECT 1 FROM DUAL;"))
    assert result.classification is Classification.STANDALONE_QUERY


# ───────── 2 — WITH (CTE) → standalone_query ─────────


def test_classifier_tags_with_cte_as_standalone_query() -> None:
    sql = "WITH t AS (SELECT 1 AS x FROM DUAL) SELECT * FROM t;"
    result = classify(_snip(sql))
    assert result.classification is Classification.STANDALONE_QUERY


# ───────── 3 — DML as standalone_query ─────────


def test_classifier_tags_insert_update_delete_merge_as_standalone_query() -> None:
    for sql in (
        "INSERT INTO orders (order_id) VALUES (1);",
        "UPDATE orders SET order_id = 2 WHERE order_id = 1;",
        "DELETE FROM orders WHERE order_id = 1;",
        "MERGE INTO t USING s ON (t.id=s.id) WHEN MATCHED THEN UPDATE SET t.x=s.x;",
    ):
        result = classify(_snip(sql))
        assert result.classification is Classification.STANDALONE_QUERY, sql


# ───────── 4 — CREATE TABLE → standalone_ddl ─────────


def test_classifier_tags_create_table_as_standalone_ddl() -> None:
    result = classify(_snip("CREATE TABLE foo (id NUMBER PRIMARY KEY);"))
    assert result.classification is Classification.STANDALONE_DDL


# ───────── 5 — CREATE INDEX variants → standalone_ddl ─────────


def test_classifier_tags_create_index_as_standalone_ddl() -> None:
    for sql in (
        "CREATE INDEX idx_x ON orders (order_doc.x);",
        "CREATE UNIQUE INDEX idx_y ON orders (order_doc.y);",
        "CREATE MULTIVALUE INDEX idx_tags ON orders o (o.order_doc.tags[*]);",
        "CREATE SEARCH INDEX idx_s ON orders (order_doc) FOR JSON;",
    ):
        result = classify(_snip(sql))
        assert result.classification is Classification.STANDALONE_DDL, sql


# ───────── 6 — CREATE JSON RELATIONAL DUALITY VIEW → standalone_ddl ─────────


def test_classifier_tags_create_json_relational_duality_view_as_standalone_ddl() -> None:
    sql = (
        "CREATE JSON RELATIONAL DUALITY VIEW order_dv AS "
        "SELECT JSON{'id': o.order_id} FROM orders o;"
    )
    result = classify(_snip(sql))
    assert result.classification is Classification.STANDALONE_DDL


# ───────── 7 — ALTER / DROP → standalone_ddl ─────────


def test_classifier_tags_alter_drop_as_standalone_ddl() -> None:
    for sql in (
        "ALTER TABLE orders ADD (extra VARCHAR2(100));",
        "DROP INDEX idx_x;",
        "DROP TABLE orders PURGE;",
    ):
        result = classify(_snip(sql))
        assert result.classification is Classification.STANDALONE_DDL, sql


# ───────── 8 — WHERE-clause fragment ─────────


def test_classifier_tags_where_fragment_as_fragment() -> None:
    sql = "WHERE JSON_EXISTS(o.order_doc, '$.items[*]?(@.unitPrice > 25)')"
    result = classify(_snip(sql))
    assert result.classification is Classification.FRAGMENT


# ───────── 9 — JSON_TABLE expression fragment ─────────


def test_classifier_tags_json_table_fragment_as_fragment() -> None:
    sql = "JSON_TABLE(o.order_doc, '$.items[*]' COLUMNS (sku VARCHAR2(50) PATH '$.sku'))"
    result = classify(_snip(sql))
    assert result.classification is Classification.FRAGMENT


# ───────── 10 — NESTED PATH fragment ─────────


def test_classifier_tags_nested_path_fragment_as_fragment() -> None:
    sql = "NESTED PATH '$.items[*]' COLUMNS (sku VARCHAR2(50) PATH '$.sku')"
    result = classify(_snip(sql))
    assert result.classification is Classification.FRAGMENT


# ───────── 11 — CYCLE clause fragment ─────────


def test_classifier_tags_cycle_clause_fragment_as_fragment() -> None:
    sql = "CYCLE id SET is_cycle TO 'Y' DEFAULT 'N'"
    result = classify(_snip(sql))
    assert result.classification is Classification.FRAGMENT


# ───────── 12 — comment-only body ─────────


def test_classifier_tags_body_with_only_comments_as_comment_only() -> None:
    sql = "-- pseudocode only\n-- not a real statement\n"
    result = classify(_snip(sql))
    assert result.classification is Classification.COMMENT_ONLY


# ───────── 13 — leading comments ignored when classifying ─────────


def test_classifier_ignores_leading_comments_when_classifying() -> None:
    sql = "-- this select finds all orders in the Belmont area\nSELECT * FROM orders;"
    result = classify(_snip(sql))
    assert result.classification is Classification.STANDALONE_QUERY


# ───────── 14 — lowercase keywords ─────────


def test_classifier_handles_lowercase_keywords() -> None:
    for sql in (
        "select 1 from dual;",
        "create table foo (id number);",
        "where json_exists(o.order_doc, '$.x')",
    ):
        # Just make sure these don't crash and produce a non-None result.
        result = classify(_snip(sql))
        assert result.classification is not None, sql


# ───────── 15 — idempotence ─────────


def test_classifier_classifies_in_a_single_pass_idempotently() -> None:
    snip = _snip("SELECT 1 FROM DUAL;")
    first = classify(snip)
    second = classify(snip)
    assert isinstance(first, ClassifiedSnippet)
    assert first.classification is second.classification
    assert first.snippet == second.snippet
