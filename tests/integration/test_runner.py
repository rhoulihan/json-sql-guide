"""Integration tests for the execution runner.

The runner takes a stream of ``DirectedSnippet`` inputs, classifies and
wraps them as needed, executes them against Oracle with per-snippet
savepoint isolation, and returns a ``Result`` per executed statement.

All tests require a live Oracle database — they skip cleanly via the
``oracle_conn`` fixture when none is reachable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from validator.directives import (
    DirectedSnippet,
    Directive,
    DirectiveSet,
)
from validator.fixture import FixtureLoader
from validator.models import Snippet
from validator.runner import Result, Runner, RunnerOptions

pytestmark = pytest.mark.requires_oracle


# ───────── helpers ─────────


def _mk(
    sql: str,
    *,
    id: str = "sql-0001",
    line: int = 1,
    section: str = "§test",
    directives: DirectiveSet | None = None,
) -> DirectedSnippet:
    return DirectedSnippet(
        snippet=Snippet(id=id, line=line, section=section, subsection=None, sql=sql),
        directives=directives or DirectiveSet(),
    )


def _factory(conn: Any) -> Callable[[str], Any]:
    """Return a conn_factory that records roles requested."""
    conn.__role_calls__ = []

    def f(role: str) -> Any:
        conn.__role_calls__.append(role)
        return conn

    return f


def _scalar(conn: Any, sql: str) -> Any:
    cur = conn.cursor()
    try:
        cur.execute(sql)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()


@pytest.fixture
def loaded(oracle_conn: Any) -> Any:
    """Reset fixture to a known state before each test."""
    FixtureLoader(oracle_conn, profiles=["base"]).load()
    return oracle_conn


# ───────── 1 — simple SELECT passes ─────────


def test_runner_executes_simple_select_and_records_pass(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk("SELECT COUNT(*) FROM orders")])
    assert len(results) == 1
    r = results[0]
    assert isinstance(r, Result)
    assert r.outcome == "pass"
    assert r.error_code is None


# ───────── 2 — ORA error recorded as fail ─────────


def test_runner_captures_ora_error_and_records_fail(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk("SELECT * FROM table_that_does_not_exist_zzz")])
    assert len(results) == 1
    r = results[0]
    assert r.outcome == "fail"
    assert r.error_code is not None
    assert r.error_code.startswith("ORA-")


# ───────── 3 — @skip directive produces skip ─────────


def test_runner_respects_skip_directive_and_records_skip(loaded: Any) -> None:
    directives = DirectiveSet(flags=frozenset({Directive.SKIP}))
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk("SELECT 1 FROM DUAL", directives=directives)])
    assert len(results) == 1
    assert results[0].outcome == "skip"


# ───────── 4 — @expect-error matches actual ─────────


def test_runner_confirms_expected_error_when_ora_code_matches(loaded: Any) -> None:
    directives = DirectiveSet(expected_error_code="ORA-00942")  # table does not exist
    runner = Runner(_factory(loaded))
    results = runner.execute(
        [_mk("SELECT * FROM table_that_does_not_exist_zzz", directives=directives)]
    )
    assert len(results) == 1
    r = results[0]
    assert r.outcome == "expected-error-confirmed"
    assert r.error_code == "ORA-00942"


# ───────── 5 — @expect-error mismatch records fail ─────────


def test_runner_records_fail_when_expected_error_does_not_match_actual(loaded: Any) -> None:
    directives = DirectiveSet(expected_error_code="ORA-99999")  # won't match
    runner = Runner(_factory(loaded))
    results = runner.execute(
        [_mk("SELECT * FROM table_that_does_not_exist_zzz", directives=directives)]
    )
    assert len(results) == 1
    r = results[0]
    assert r.outcome == "fail"
    # actual error code should be captured
    assert r.error_code is not None
    assert r.error_code != "ORA-99999"


# ───────── 6 — DML rolled back via savepoint ─────────


def test_runner_rolls_back_dml_between_snippets_via_savepoint(loaded: Any) -> None:
    baseline = _scalar(loaded, "SELECT COUNT(*) FROM orders")

    runner = Runner(_factory(loaded))
    runner.execute(
        [
            _mk(
                "INSERT INTO orders (order_doc) VALUES (JSON('{\"orderId\": 9999}'))",
                id="sql-0001",
            ),
            _mk("SELECT COUNT(*) FROM orders", id="sql-0002"),
        ]
    )

    # After the run, the INSERT must have been rolled back.
    after = _scalar(loaded, "SELECT COUNT(*) FROM orders")
    assert after == baseline


# ───────── 7 — DDL artifacts cleaned up at end ─────────


def test_runner_executes_ddl_in_sandbox_and_drops_artifacts_at_end(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    runner.execute([_mk("CREATE TABLE runner_sandbox_t (x NUMBER)", id="sql-0001")])

    # Table must not exist after the run — it was cleaned up.
    cur = loaded.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM user_tables WHERE table_name = 'RUNNER_SANDBOX_T'")
        (count,) = cur.fetchone()
        assert count == 0
    finally:
        cur.close()


# ───────── 8 — row count recorded for SELECT ─────────


def test_runner_records_row_count_for_select_statements(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk("SELECT * FROM orders")])
    assert len(results) == 1
    r = results[0]
    assert r.outcome == "pass"
    assert r.rows_returned == 10  # base seed inserts 10 orders


# ───────── 9 — elapsed_ms within expected range ─────────


def test_runner_records_elapsed_ms_within_expected_range(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk("SELECT 1 FROM DUAL")])
    assert len(results) == 1
    r = results[0]
    # Non-negative and under 10 seconds is enough to guard against obvious bugs.
    assert r.elapsed_ms >= 0
    assert r.elapsed_ms < 10_000


# ───────── 10 — multi-statement block yields one result per statement ─────────


def test_runner_splits_multi_statement_block_and_records_per_statement_outcomes(
    loaded: Any,
) -> None:
    sql = "SELECT COUNT(*) FROM orders;\nSELECT id FROM orders FETCH FIRST 1 ROW ONLY"
    runner = Runner(_factory(loaded))
    results = runner.execute([_mk(sql)])
    assert len(results) == 2
    assert all(r.outcome == "pass" for r in results)
    assert results[0].id != results[1].id  # distinct per-statement ids


# ───────── 11 — DBA connection used when @runs-as DBA ─────────


def test_runner_uses_dba_connection_when_runs_as_dba_directive_present(loaded: Any) -> None:
    directives = DirectiveSet(flags=frozenset({Directive.RUNS_AS_DBA}))
    factory = _factory(loaded)
    runner = Runner(factory)
    runner.execute([_mk("SELECT 1 FROM DUAL", directives=directives)])
    roles = loaded.__role_calls__
    assert "dba" in roles


# ───────── 12 — snippets processed in catalog order ─────────


def test_runner_processes_snippets_in_catalog_order(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute(
        [
            _mk("SELECT 1 FROM DUAL", id="sql-0001", line=10),
            _mk("SELECT 2 FROM DUAL", id="sql-0002", line=20),
            _mk("SELECT 3 FROM DUAL", id="sql-0003", line=30),
        ]
    )
    ids = [r.id for r in results]
    assert ids == ["sql-0001", "sql-0002", "sql-0003"]


# ───────── 13 — runner continues after failure by default ─────────


def test_runner_continues_after_failure_by_default(loaded: Any) -> None:
    runner = Runner(_factory(loaded))
    results = runner.execute(
        [
            _mk("SELECT * FROM table_that_does_not_exist_zzz", id="sql-0001"),
            _mk("SELECT 1 FROM DUAL", id="sql-0002"),
            _mk("SELECT 2 FROM DUAL", id="sql-0003"),
        ]
    )
    outcomes = [r.outcome for r in results]
    assert outcomes == ["fail", "pass", "pass"]


# ───────── 14 — fast-fail stops after first failure ─────────


def test_runner_fast_fails_when_fast_fail_flag_is_set(loaded: Any) -> None:
    runner = Runner(_factory(loaded), options=RunnerOptions(fast_fail=True))
    results = runner.execute(
        [
            _mk("SELECT 1 FROM DUAL", id="sql-0001"),
            _mk("SELECT * FROM table_that_does_not_exist_zzz", id="sql-0002"),
            _mk("SELECT 2 FROM DUAL", id="sql-0003"),  # must NOT run
        ]
    )
    outcomes = [r.outcome for r in results]
    assert outcomes == ["pass", "fail"]
