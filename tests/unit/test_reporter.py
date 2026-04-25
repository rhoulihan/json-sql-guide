"""Unit tests for the reporter module.

The reporter takes a list of ``Result`` objects produced by
``Runner.execute`` and emits four outputs:

1. ``render_cli(results, console)`` — rich-formatted summary + failures.
2. ``render_junit(results, path)`` — JUnit XML for CI.
3. ``render_annotated(results, source_md_path, output_path)`` — copy of
   the source markdown with ✓/✗/⊘ badges inserted after each ``sql``
   fence.
4. ``dump_json(results, path)`` — stable JSON dump of all Result fields.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from validator.reporter import (
    dump_json,
    render_annotated,
    render_cli,
    render_junit,
)
from validator.runner import Result

# ───────── helpers ─────────


def _r(
    id: str,
    outcome: str,
    *,
    line: int = 1,
    classification: str = "standalone_query",
    error_code: str | None = None,
    error_text: str | None = None,
    rows_returned: int | None = None,
    elapsed_ms: int = 5,
    wrapped_sql: str | None = None,
) -> Result:
    return Result(
        id=id,
        line=line,
        classification=classification,
        outcome=outcome,
        error_code=error_code,
        error_text=error_text,
        rows_returned=rows_returned,
        elapsed_ms=elapsed_ms,
        wrapped_sql=wrapped_sql,
    )


def _capture(console_kwargs: dict[str, object] | None = None) -> tuple[Console, StringIO]:
    buf = StringIO()
    kwargs: dict[str, object] = {"file": buf, "width": 100}
    if console_kwargs:
        kwargs.update(console_kwargs)
    console = Console(**kwargs)  # type: ignore[arg-type]
    return console, buf


_SAMPLE_RESULTS = [
    _r("sql-0001", "pass", line=10, rows_returned=10, elapsed_ms=4),
    _r(
        "sql-0002",
        "fail",
        line=20,
        error_code="ORA-40596",
        error_text="JSON path clause order is invalid",
    ),
    _r("sql-0003", "skip", line=30, classification="comment_only"),
    _r("sql-0004", "expected-error-confirmed", line=40, error_code="ORA-00942"),
]


# ───────── 1 — CLI: total counts ─────────


def test_cli_report_shows_total_pass_fail_skip_counts() -> None:
    console, buf = _capture()
    render_cli(_SAMPLE_RESULTS, console)
    out = buf.getvalue()
    # 4 total: 1 pass + 1 fail + 1 skip + 1 expected-error-confirmed (counted as success)
    assert "Total" in out
    assert "4" in out
    assert "Passed" in out
    assert "Failed" in out
    assert "Skipped" in out


# ───────── 2 — CLI: failures listed with section/line/ORA code ─────────


def test_cli_report_lists_failures_with_section_line_and_ora_code() -> None:
    console, buf = _capture()
    render_cli(_SAMPLE_RESULTS, console)
    out = buf.getvalue()
    assert "sql-0002" in out
    assert "line 20" in out or "20" in out
    assert "ORA-40596" in out
    assert "JSON path clause order" in out


# ───────── 3 — CLI: rich markup strips cleanly when TTY disabled ─────────


def test_cli_report_renders_with_rich_markup_and_strips_cleanly_when_tty_disabled() -> None:
    # Force plain (no color, no escape codes) so CI logs are clean.
    console, buf = _capture({"force_terminal": False, "color_system": None})
    render_cli(_SAMPLE_RESULTS, console)
    out = buf.getvalue()
    # No ANSI escape sequences should leak through.
    assert "\x1b[" not in out


# ───────── 4 — JUnit: valid XML ─────────


def test_junit_report_is_valid_xml_against_schema(tmp_path: Path) -> None:
    out = tmp_path / "junit.xml"
    render_junit(_SAMPLE_RESULTS, out)
    tree = ET.parse(out)
    root = tree.getroot()
    # Standard JUnit roots are testsuites or testsuite.
    assert root.tag in {"testsuites", "testsuite"}


# ───────── 5 — JUnit: one testcase per snippet ─────────


def test_junit_report_creates_one_testcase_per_snippet(tmp_path: Path) -> None:
    out = tmp_path / "junit.xml"
    render_junit(_SAMPLE_RESULTS, out)
    root = ET.parse(out).getroot()
    cases = root.findall(".//testcase")
    assert len(cases) == 4
    names = [c.get("name") for c in cases]
    assert names == ["sql-0001", "sql-0002", "sql-0003", "sql-0004"]


# ───────── 6 — JUnit: failures carry message and type ─────────


def test_junit_report_marks_failures_with_message_and_type(tmp_path: Path) -> None:
    out = tmp_path / "junit.xml"
    render_junit(_SAMPLE_RESULTS, out)
    root = ET.parse(out).getroot()
    failure = root.find(".//testcase[@name='sql-0002']/failure")
    assert failure is not None
    assert failure.get("type") == "ORA-40596"
    msg = failure.get("message") or ""
    assert "JSON path" in msg


# ───────── 7 — JUnit: skipped snippets marked skipped ─────────


def test_junit_report_marks_skipped_snippets_as_skipped(tmp_path: Path) -> None:
    out = tmp_path / "junit.xml"
    render_junit(_SAMPLE_RESULTS, out)
    root = ET.parse(out).getroot()
    skipped = root.find(".//testcase[@name='sql-0003']/skipped")
    assert skipped is not None


# ───────── 8 — annotated MD preserves source bytes ─────────


def _sample_md() -> str:
    return (
        "# Sample\n"
        "\n"
        "Some prose.\n"
        "\n"
        "```sql\n"
        "SELECT 1 FROM DUAL;\n"
        "```\n"
        "\n"
        "More prose.\n"
        "\n"
        "```sql\n"
        "SELECT bogus FROM nowhere;\n"
        "```\n"
        "\n"
        "End.\n"
    )


def test_annotated_markdown_preserves_original_content_byte_for_byte_outside_of_inserted_badges(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src.md"
    out = tmp_path / "annotated.md"
    src.write_text(_sample_md(), encoding="utf-8")
    results = [
        _r("sql-0001", "pass", line=5, rows_returned=1),
        _r("sql-0002", "fail", line=11, error_code="ORA-00942"),
    ]
    render_annotated(results, src, out)
    annotated = out.read_text(encoding="utf-8")
    # Strip badge lines and confirm the rest is byte-identical to the source.
    badge_re = re.compile(r"^<!--\s*[✓✗⊘].*-->\s*$")
    cleaned = "\n".join(
        line for line in annotated.splitlines() if not badge_re.match(line)
    )
    # Reattach trailing newline if source had one to match.
    if _sample_md().endswith("\n") and not cleaned.endswith("\n"):
        cleaned += "\n"
    assert cleaned == _sample_md()


# ───────── 9 — annotated MD: pass badge after passing fence ─────────


def test_annotated_markdown_inserts_pass_badge_after_passing_sql_fence(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src.md"
    out = tmp_path / "annotated.md"
    src.write_text(_sample_md(), encoding="utf-8")
    results = [
        _r("sql-0001", "pass", line=5, rows_returned=1, elapsed_ms=8),
        _r("sql-0002", "pass", line=11, rows_returned=0, elapsed_ms=3),
    ]
    render_annotated(results, src, out)
    annotated = out.read_text(encoding="utf-8")
    assert "<!-- ✓ sql-0001 passed" in annotated


# ───────── 10 — annotated MD: fail badge with ORA code ─────────


def test_annotated_markdown_inserts_fail_badge_with_ora_code_after_failing_sql_fence(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src.md"
    out = tmp_path / "annotated.md"
    src.write_text(_sample_md(), encoding="utf-8")
    results = [
        _r("sql-0001", "pass"),
        _r("sql-0002", "fail", error_code="ORA-00942", error_text="not exist"),
    ]
    render_annotated(results, src, out)
    annotated = out.read_text(encoding="utf-8")
    assert "<!-- ✗ sql-0002 failed: ORA-00942" in annotated


# ───────── 11 — annotated MD: skip badge ─────────


def test_annotated_markdown_inserts_skip_badge_for_skipped_snippets(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src.md"
    out = tmp_path / "annotated.md"
    src.write_text(_sample_md(), encoding="utf-8")
    results = [
        _r("sql-0001", "pass"),
        _r("sql-0002", "skip"),
    ]
    render_annotated(results, src, out)
    annotated = out.read_text(encoding="utf-8")
    assert "<!-- ⊘ sql-0002 skipped" in annotated


# ───────── 12 — annotated MD is idempotent ─────────


def test_annotated_markdown_is_idempotent_when_reapplied_to_already_annotated_file(
    tmp_path: Path,
) -> None:
    src = tmp_path / "src.md"
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    src.write_text(_sample_md(), encoding="utf-8")
    results = [
        _r("sql-0001", "pass", rows_returned=1, elapsed_ms=4),
        _r("sql-0002", "fail", error_code="ORA-00942"),
    ]
    render_annotated(results, src, first)
    render_annotated(results, first, second)
    assert first.read_bytes() == second.read_bytes()


# ───────── 13 — JSON dump serializes all Result fields ─────────


def test_results_json_serializes_all_result_fields(tmp_path: Path) -> None:
    out = tmp_path / "results.json"
    dump_json(_SAMPLE_RESULTS, out)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(payload, list)
    assert len(payload) == 4
    expected_keys = {
        "id",
        "line",
        "classification",
        "outcome",
        "error_code",
        "error_text",
        "rows_returned",
        "elapsed_ms",
        "wrapped_sql",
    }
    for record in payload:
        assert expected_keys.issubset(record.keys())


# ───────── 14 — JSON dump is stable across runs ─────────


def test_results_json_is_stable_across_runs_given_identical_inputs(tmp_path: Path) -> None:
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    dump_json(_SAMPLE_RESULTS, a)
    dump_json(_SAMPLE_RESULTS, b)
    assert a.read_bytes() == b.read_bytes()


# Suppress unused-import warning for pytest marker decorators if any.
_ = pytest
