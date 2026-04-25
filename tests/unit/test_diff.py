"""Unit tests for the diff module.

``diff_results(prev, curr)`` returns a structured diff. The same diff
can be rendered as Markdown via ``render_diff_md`` and used to derive
an exit code via ``diff_exit_code`` (non-zero when regressions exist).
"""

from __future__ import annotations

from validator.diff import (
    ResultDiff,
    diff_exit_code,
    diff_results,
    render_diff_md,
)
from validator.runner import Result

# ───────── helpers ─────────


def _r(
    id: str,
    outcome: str,
    *,
    line: int = 1,
    error_code: str | None = None,
    rows_returned: int | None = None,
    elapsed_ms: int = 5,
) -> Result:
    return Result(
        id=id,
        line=line,
        classification="standalone_query",
        outcome=outcome,
        error_code=error_code,
        rows_returned=rows_returned,
        elapsed_ms=elapsed_ms,
    )


# ───────── 1 — identical results → no changes ─────────


def test_diff_reports_no_changes_when_results_are_identical() -> None:
    prev = [_r("sql-0001", "pass"), _r("sql-0002", "pass")]
    curr = [_r("sql-0001", "pass"), _r("sql-0002", "pass")]
    diff = diff_results(prev, curr)
    assert isinstance(diff, ResultDiff)
    assert diff.regressions == []
    assert diff.improvements == []
    assert diff.newly_skipped == []
    assert diff.newly_added == []
    assert diff.removed == []
    assert diff.unchanged_count == 2


# ───────── 2 — newly failing snippet ─────────


def test_diff_reports_newly_failing_snippet() -> None:
    prev = [_r("sql-0001", "pass")]
    curr = [_r("sql-0001", "fail", error_code="ORA-40596")]
    diff = diff_results(prev, curr)
    assert len(diff.regressions) == 1
    change = diff.regressions[0]
    assert change.id == "sql-0001"
    assert change.previous.outcome == "pass"
    assert change.current.outcome == "fail"
    assert change.current.error_code == "ORA-40596"


# ───────── 3 — newly passing snippet ─────────


def test_diff_reports_newly_passing_snippet() -> None:
    prev = [_r("sql-0001", "fail", error_code="ORA-40596")]
    curr = [_r("sql-0001", "pass")]
    diff = diff_results(prev, curr)
    assert len(diff.improvements) == 1
    change = diff.improvements[0]
    assert change.id == "sql-0001"
    assert change.previous.outcome == "fail"
    assert change.current.outcome == "pass"


# ───────── 4 — newly skipped snippet ─────────


def test_diff_reports_newly_skipped_snippet() -> None:
    prev = [_r("sql-0001", "pass")]
    curr = [_r("sql-0001", "skip")]
    diff = diff_results(prev, curr)
    assert len(diff.newly_skipped) == 1
    assert diff.newly_skipped[0].id == "sql-0001"


# ───────── 5 — added snippet ─────────


def test_diff_reports_snippet_added_since_previous_run() -> None:
    prev = [_r("sql-0001", "pass")]
    curr = [_r("sql-0001", "pass"), _r("sql-0002", "pass")]
    diff = diff_results(prev, curr)
    assert len(diff.newly_added) == 1
    assert diff.newly_added[0].id == "sql-0002"


# ───────── 6 — removed snippet ─────────


def test_diff_reports_snippet_removed_since_previous_run() -> None:
    prev = [_r("sql-0001", "pass"), _r("sql-0002", "pass")]
    curr = [_r("sql-0001", "pass")]
    diff = diff_results(prev, curr)
    assert len(diff.removed) == 1
    assert diff.removed[0].id == "sql-0002"


# ───────── 7 — markdown output uses section headings ─────────


def test_diff_emits_markdown_with_section_grouping() -> None:
    prev = [
        _r("sql-0001", "pass"),
        _r("sql-0002", "fail", error_code="ORA-1"),
        _r("sql-0003", "pass"),
    ]
    curr = [
        _r("sql-0001", "fail", error_code="ORA-2"),  # regression
        _r("sql-0002", "pass"),                       # improvement
        _r("sql-0004", "pass"),                       # added
    ]
    diff = diff_results(prev, curr)
    md = render_diff_md(diff)
    # Each category becomes its own H2 section.
    assert "## Regressions" in md
    assert "## Improvements" in md
    assert "## Removed" in md
    assert "## Added" in md
    # And the regression line carries the new ORA code.
    assert "ORA-2" in md


# ───────── 8 — elapsed_ms fluctuation ignored by default ─────────


def test_diff_ignores_elapsed_ms_fluctuation_by_default() -> None:
    prev = [_r("sql-0001", "pass", elapsed_ms=4)]
    curr = [_r("sql-0001", "pass", elapsed_ms=347)]
    diff = diff_results(prev, curr)
    assert diff.regressions == []
    assert diff.improvements == []
    assert diff.unchanged_count == 1


# ───────── 9 — exit code nonzero on regressions ─────────


def test_diff_exit_code_is_nonzero_when_regressions_exist() -> None:
    prev = [_r("sql-0001", "pass")]
    curr = [_r("sql-0001", "fail", error_code="ORA-40596")]
    diff = diff_results(prev, curr)
    assert diff_exit_code(diff) != 0


# ───────── 10 — exit code zero when only improvements ─────────


def test_diff_exit_code_is_zero_when_only_improvements_exist() -> None:
    prev = [_r("sql-0001", "fail", error_code="ORA-40596")]
    curr = [_r("sql-0001", "pass")]
    diff = diff_results(prev, curr)
    assert diff_exit_code(diff) == 0
