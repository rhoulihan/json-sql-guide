"""Execution runner — Oracle-backed snippet runner with per-snippet isolation.

Takes a stream of :class:`~validator.directives.DirectedSnippet` inputs
and returns one :class:`Result` per executed SQL statement. A snippet
that contains multiple ``;``-separated statements produces one Result
per statement, with suffixed ids (``sql-0012[1]``, ``sql-0012[2]``).

Isolation model
---------------

Before each snippet we set a uniquely-named savepoint and always roll
back to it afterwards. DML is therefore invisible to subsequent snippets
even on the happy path. DDL auto-commits in Oracle so savepoints don't
help — instead the runner tracks every object it creates (TABLE, INDEX,
VIEW, MATERIALIZED VIEW, JSON RELATIONAL DUALITY VIEW) and drops them
during :meth:`Runner.execute` teardown.

Directive handling
------------------

* ``@skip`` — snippet is not executed; Result carries ``outcome="skip"``.
* ``@expect-error ORA-NNNNN`` — a matching ORA error flips outcome to
  ``expected-error-confirmed``; any other error is a fail.
* ``@runs-as DBA`` — the runner calls ``conn_factory("dba")`` to obtain
  the connection for this snippet instead of the default role.
"""

from __future__ import annotations

import contextlib
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from validator.classifier import Classification, ClassifiedSnippet, classify
from validator.directives import DirectedSnippet, Directive
from validator.wraps import wrap

__all__ = ["Result", "Runner", "RunnerOptions"]

ConnFactory = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class Result:
    """Outcome of executing one SQL statement.

    Matches the shape documented in requirements §7.3. A single
    :class:`~validator.directives.DirectedSnippet` may produce multiple
    Results when its body contains multiple ``;``-separated statements.
    """

    id: str
    line: int
    classification: str
    outcome: str  # pass | fail | skip | expected-error-confirmed
    error_code: str | None = None
    error_text: str | None = None
    rows_returned: int | None = None
    elapsed_ms: int = 0
    wrapped_sql: str | None = None


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Runner configuration."""

    fast_fail: bool = False


@dataclass(slots=True)
class _DDLArtifact:
    kind: str  # TABLE, INDEX, VIEW, MATERIALIZED VIEW, ...
    name: str


class Runner:
    """Execute snippets against Oracle with per-snippet isolation."""

    def __init__(
        self,
        conn_factory: ConnFactory,
        options: RunnerOptions | None = None,
    ) -> None:
        self._conn_factory = conn_factory
        self._options = options or RunnerOptions()
        self._conns: dict[str, Any] = {}
        self._savepoint_counter = 0

    def execute(self, snippets: Iterable[DirectedSnippet]) -> list[Result]:
        """Run every snippet, returning one Result per statement.

        Stops early if :attr:`RunnerOptions.fast_fail` is set and any
        Result comes back with ``outcome="fail"``. Cleans up DDL
        artifacts it created before returning.
        """
        results: list[Result] = []
        artifacts: list[_DDLArtifact] = []
        should_stop = False

        for directed in snippets:
            if should_stop:
                break
            for result in self._run_directed(directed, artifacts):
                results.append(result)
                if self._options.fast_fail and result.outcome == "fail":
                    should_stop = True
                    break

        self._cleanup(artifacts)
        return results

    # ───────── per-snippet orchestration ─────────

    def _run_directed(
        self,
        directed: DirectedSnippet,
        artifacts: list[_DDLArtifact],
    ) -> list[Result]:
        snippet = directed.snippet
        classified = classify(snippet)
        classification_str = classified.classification.value

        if Directive.SKIP in directed.directives:
            return [
                Result(
                    id=snippet.id,
                    line=snippet.line,
                    classification=classification_str,
                    outcome="skip",
                )
            ]

        if classified.classification is Classification.COMMENT_ONLY:
            return [
                Result(
                    id=snippet.id,
                    line=snippet.line,
                    classification=classification_str,
                    outcome="skip",
                )
            ]

        executable_sql, wrapped_sql_for_result = self._prepare_sql(directed, classified)
        statements = _split_statements(executable_sql)
        multi = len(statements) > 1

        role = "dba" if Directive.RUNS_AS_DBA in directed.directives else "default"
        conn = self._get_conn(role)

        results: list[Result] = []
        for i, stmt in enumerate(statements, start=1):
            stmt_id = f"{snippet.id}[{i}]" if multi else snippet.id
            result = self._execute_statement(
                conn=conn,
                stmt=stmt,
                snippet_id=stmt_id,
                line=snippet.line,
                classification=classification_str,
                expected_error_code=directed.directives.expected_error_code,
                wrapped_sql=wrapped_sql_for_result,
                artifacts=artifacts,
            )
            results.append(result)
        return results

    def _prepare_sql(
        self,
        directed: DirectedSnippet,
        classified: ClassifiedSnippet,
    ) -> tuple[str, str | None]:
        """Return (sql_to_execute, wrapped_sql_for_result).

        For fragments (or snippets marked ``@fragment``), wrap via the
        fragment registry. For standalone statements, pass through.
        """
        is_fragment = (
            classified.classification is Classification.FRAGMENT
            or Directive.FORCE_FRAGMENT in directed.directives
        )
        if is_fragment:
            wrapped = wrap(directed)
            return wrapped.executable_sql, wrapped.executable_sql
        return directed.snippet.sql, None

    # ───────── statement execution ─────────

    def _execute_statement(
        self,
        *,
        conn: Any,
        stmt: str,
        snippet_id: str,
        line: int,
        classification: str,
        expected_error_code: str | None,
        wrapped_sql: str | None,
        artifacts: list[_DDLArtifact],
    ) -> Result:
        savepoint = self._next_savepoint()
        cur = conn.cursor()
        start_ns = time.perf_counter_ns()
        try:
            cur.execute(f"SAVEPOINT {savepoint}")
            cur.execute(stmt)
            rows_returned = _try_fetch_count(cur)
            elapsed_ms = _elapsed_ms(start_ns)

            # Track any DDL artifact we just created for teardown.
            artifact = _parse_ddl_artifact(stmt)
            if artifact is not None:
                artifacts.append(artifact)

            if expected_error_code is not None:
                # Expected an error but got success — fail.
                return Result(
                    id=snippet_id,
                    line=line,
                    classification=classification,
                    outcome="fail",
                    error_text=(
                        f"expected error {expected_error_code} but statement succeeded"
                    ),
                    rows_returned=rows_returned,
                    elapsed_ms=elapsed_ms,
                    wrapped_sql=wrapped_sql,
                )

            return Result(
                id=snippet_id,
                line=line,
                classification=classification,
                outcome="pass",
                rows_returned=rows_returned,
                elapsed_ms=elapsed_ms,
                wrapped_sql=wrapped_sql,
            )
        except Exception as exc:
            elapsed_ms = _elapsed_ms(start_ns)
            code, message = _extract_oracle_error(exc)
            outcome = (
                "expected-error-confirmed"
                if expected_error_code is not None and code == expected_error_code
                else "fail"
            )
            return Result(
                id=snippet_id,
                line=line,
                classification=classification,
                outcome=outcome,
                error_code=code,
                error_text=message,
                elapsed_ms=elapsed_ms,
                wrapped_sql=wrapped_sql,
            )
        finally:
            # Always roll back to the savepoint so DML is invisible
            # to later snippets. DDL already auto-committed; teardown
            # handles those artifacts, and the rollback here may no
            # longer find a valid savepoint — either is harmless.
            with contextlib.suppress(Exception):
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.close()

    # ───────── helpers ─────────

    def _get_conn(self, role: str) -> Any:
        if role not in self._conns:
            self._conns[role] = self._conn_factory(role)
        return self._conns[role]

    def _next_savepoint(self) -> str:
        self._savepoint_counter += 1
        return f"val_sp_{self._savepoint_counter}"

    def _cleanup(self, artifacts: list[_DDLArtifact]) -> None:
        if not artifacts:
            return
        conn = self._get_conn("default")
        cur = conn.cursor()
        try:
            # Drop in reverse creation order to satisfy FK-ish deps.
            # Best-effort teardown — a missing object is fine, as is
            # a dependency that has to be dropped first.
            for artifact in reversed(artifacts):
                with contextlib.suppress(Exception):
                    cur.execute(_drop_statement(artifact))
            conn.commit()
        finally:
            cur.close()


# ───────── module-level helpers ─────────


def _elapsed_ms(start_ns: int) -> int:
    return max(0, (time.perf_counter_ns() - start_ns) // 1_000_000)


def _try_fetch_count(cur: Any) -> int | None:
    """Return row count for a SELECT-style cursor; ``None`` for DDL/DML."""
    desc = getattr(cur, "description", None)
    if not desc:
        return None
    try:
        rows = cur.fetchall()
    except Exception:
        return None
    return len(rows)


_ORA_CODE_RE = re.compile(r"ORA-(\d{4,5})")


def _extract_oracle_error(exc: Exception) -> tuple[str | None, str]:
    """Pull an ``ORA-NNNNN`` code and message out of a DB exception."""
    text = str(exc)
    # python-oracledb puts an _Error object in exc.args[0] with .code / .message.
    args = getattr(exc, "args", ())
    if args:
        err = args[0]
        code = getattr(err, "code", None)
        message = getattr(err, "message", None)
        if isinstance(code, int):
            return f"ORA-{code:05d}", message or text
    # Fallback: scan the stringified exception.
    match = _ORA_CODE_RE.search(text)
    if match is not None:
        digits = match.group(1)
        return f"ORA-{int(digits):05d}", text
    return None, text


def _split_statements(sql: str) -> list[str]:
    """Split on ``;`` at top level, respecting single-quoted strings.

    Leaves PL/SQL blocks alone — they should arrive already wrapped
    with an explicit ``@wrap-as`` directive or be passed in as a single
    statement without internal ``;`` that the runner shouldn't split.
    For plain DDL/DML/SELECT the naive split is correct because
    Oracle's ``;`` terminators are never required inside single
    statements.
    """
    parts: list[str] = []
    buf: list[str] = []
    in_string = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'":
            # handle '' escaped quote inside a string
            if in_string and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append("''")
                i += 2
                continue
            in_string = not in_string
            buf.append(ch)
        elif ch == ";" and not in_string:
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf.clear()
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    # Drop fragments that are nothing but ``-- ...`` line comments —
    # a trailing inline comment after the last ``;`` shouldn't become
    # an executable statement.
    parts = [p for p in parts if _strip_leading_comments(p).strip()]
    return parts or [sql.strip()]


# ───────── DDL artifact tracking ─────────


_DDL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "JSON RELATIONAL DUALITY VIEW",
        re.compile(
            r"^\s*CREATE(?:\s+OR\s+REPLACE)?\s+JSON\s+RELATIONAL\s+DUALITY\s+VIEW\s+"
            r"([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "MATERIALIZED VIEW",
        re.compile(
            r"^\s*CREATE(?:\s+OR\s+REPLACE)?\s+MATERIALIZED\s+VIEW\s+"
            r"([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "VIEW",
        re.compile(
            r"^\s*CREATE(?:\s+OR\s+REPLACE)?\s+VIEW\s+"
            r"([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "SEARCH INDEX",
        re.compile(
            r"^\s*CREATE\s+SEARCH\s+INDEX\s+([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "INDEX",
        re.compile(
            r"^\s*CREATE(?:\s+UNIQUE)?(?:\s+BITMAP)?\s+INDEX\s+"
            r"([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
    (
        "TABLE",
        re.compile(
            r"^\s*CREATE(?:\s+GLOBAL\s+TEMPORARY)?\s+TABLE\s+"
            r"([A-Za-z_][A-Za-z0-9_$#.]*)",
            re.IGNORECASE,
        ),
    ),
]


def _parse_ddl_artifact(sql: str) -> _DDLArtifact | None:
    stripped = _strip_leading_comments(sql)
    for kind, pat in _DDL_PATTERNS:
        m = pat.match(stripped)
        if m is not None:
            return _DDLArtifact(kind=kind, name=m.group(1))
    return None


_COMMENT_LINE = re.compile(r"^\s*--.*$")


def _strip_leading_comments(sql: str) -> str:
    lines = sql.splitlines()
    first = 0
    for i, line in enumerate(lines):
        if _COMMENT_LINE.match(line) or not line.strip():
            continue
        first = i
        break
    else:
        return ""
    return "\n".join(lines[first:])


def _drop_statement(artifact: _DDLArtifact) -> str:
    if artifact.kind == "TABLE":
        return f"DROP TABLE {artifact.name} CASCADE CONSTRAINTS PURGE"
    if artifact.kind == "MATERIALIZED VIEW":
        return f"DROP MATERIALIZED VIEW {artifact.name}"
    return f"DROP {artifact.kind} {artifact.name}"


