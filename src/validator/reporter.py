"""Reporter — render Result lists to humans and machines.

Four entry points:

* :func:`render_cli` — rich-formatted summary on a console.
* :func:`render_junit` — standard JUnit XML for CI.
* :func:`render_annotated` — copy of the source markdown with ✓/✗/⊘
  badges inserted after each ``sql`` fence. Idempotent when re-applied.
* :func:`dump_json` — stable JSON dump of every Result field.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from rich.table import Table

from validator.runner import Result

if TYPE_CHECKING:
    from rich.console import Console

__all__ = ["dump_json", "render_annotated", "render_cli", "render_junit"]

_SUCCESS_OUTCOMES = frozenset({"pass", "expected-error-confirmed"})
_BADGE_SYMBOL = {
    "pass": "✓",
    "expected-error-confirmed": "✓",
    "fail": "✗",
    "skip": "⊘",
}


# ───────── CLI ─────────


def render_cli(results: Iterable[Result], console: Console) -> None:
    """Print a summary + failures section using ``rich``.

    Counts ``expected-error-confirmed`` as a pass — the directive
    asserted an error and got the asserted error.
    """
    rs = list(results)
    total = len(rs)
    passed = sum(1 for r in rs if r.outcome in _SUCCESS_OUTCOMES)
    failed = sum(1 for r in rs if r.outcome == "fail")
    skipped = sum(1 for r in rs if r.outcome == "skip")

    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_row("Total", str(total))
    summary.add_row("Passed", str(passed))
    summary.add_row("Failed", str(failed))
    summary.add_row("Skipped", str(skipped))
    console.print(summary)

    if failed == 0:
        return

    console.print()
    console.print("FAILURES")
    console.print("─" * 68)
    for r in rs:
        if r.outcome != "fail":
            continue
        code = r.error_code or "(no ORA code)"
        text = r.error_text or ""
        console.print(f"{r.id}  line {r.line}")
        console.print(f"  {code}: {text}")


# ───────── JUnit ─────────


def render_junit(results: Iterable[Result], path: Path) -> None:
    """Write a JUnit XML report to *path*.

    Layout::

        <testsuites>
          <testsuite name=... tests=... failures=... skipped=...>
            <testcase name=sql-0001 time=...>
              [<failure type=ORA-NNNNN message=...>...</failure>
               | <skipped/>]
            </testcase>
            ...
          </testsuite>
        </testsuites>
    """
    rs = list(results)
    total = len(rs)
    failures = sum(1 for r in rs if r.outcome == "fail")
    skipped = sum(1 for r in rs if r.outcome == "skip")

    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        attrib={
            "name": "json-sql-guide",
            "tests": str(total),
            "failures": str(failures),
            "skipped": str(skipped),
        },
    )
    for r in rs:
        case = ET.SubElement(
            suite,
            "testcase",
            attrib={
                "name": r.id,
                "classname": r.classification,
                "time": f"{r.elapsed_ms / 1000:.3f}",
            },
        )
        if r.outcome == "fail":
            ET.SubElement(
                case,
                "failure",
                attrib={
                    "type": r.error_code or "UnknownError",
                    "message": r.error_text or "",
                },
            )
        elif r.outcome == "skip":
            ET.SubElement(case, "skipped")

    ET.indent(root, space="  ")
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)


# ───────── Annotated markdown ─────────

_FENCE_OPEN = re.compile(r"^```sql\s*$")
_FENCE_CLOSE = re.compile(r"^```\s*$")
_BADGE_LINE = re.compile(r"^<!--\s*[✓✗⊘].*-->\s*$")


def render_annotated(
    results: Iterable[Result],
    source_md_path: Path,
    output_path: Path,
) -> None:
    """Copy *source_md_path* to *output_path* with ✓/✗/⊘ badges inserted.

    Snippets are matched by sequential index — the Nth ``sql`` fence in
    the source maps to ``sql-{N:04d}``. Existing badge lines (matching
    ``<!-- ✓/✗/⊘ ... -->``) are replaced rather than duplicated, which
    makes re-running the annotator byte-for-byte idempotent.
    """
    by_id = {r.id: r for r in _aggregate_per_snippet(results)}

    # Use split('\n') (not splitlines) so a trailing newline survives
    # round-trip via "\n".join.
    text = source_md_path.read_text(encoding="utf-8")
    lines = text.split("\n")

    out_lines: list[str] = []
    snippet_index = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        out_lines.append(line)
        i += 1
        if not _FENCE_OPEN.match(line):
            continue

        # Copy the body until the closing fence, inclusive.
        while i < len(lines):
            inner = lines[i]
            out_lines.append(inner)
            i += 1
            if _FENCE_CLOSE.match(inner):
                break

        snippet_index += 1
        sid = f"sql-{snippet_index:04d}"
        result = by_id.get(sid)
        new_badge = _format_badge(sid, result) if result is not None else None

        # If a badge already exists immediately after the fence, replace
        # it (or preserve if we have nothing new). Otherwise insert.
        if i < len(lines) and _BADGE_LINE.match(lines[i]):
            if new_badge is not None:
                out_lines.append(new_badge)
            else:
                out_lines.append(lines[i])
            i += 1
        elif new_badge is not None:
            out_lines.append(new_badge)

    output_path.write_text("\n".join(out_lines), encoding="utf-8")


def _aggregate_per_snippet(results: Iterable[Result]) -> list[Result]:
    """Collapse multi-statement Results (``sql-NNNN[k]``) to one per snippet.

    For multi-statement snippets the snippet's outcome is the worst:
    fail > skip > expected-error-confirmed > pass. The first matching
    Result's metadata is preserved.
    """
    suffix = re.compile(r"^(sql-\d+)\[\d+\]$")
    grouped: dict[str, list[Result]] = {}
    order: list[str] = []
    for r in results:
        m = suffix.match(r.id)
        key = m.group(1) if m else r.id
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(r)

    out: list[Result] = []
    for key in order:
        bucket = grouped[key]
        if len(bucket) == 1 and bucket[0].id == key:
            out.append(bucket[0])
            continue
        # Pick the worst outcome and surface its details.
        worst = _worst_outcome(bucket)
        out.append(
            Result(
                id=key,
                line=bucket[0].line,
                classification=bucket[0].classification,
                outcome=worst.outcome,
                error_code=worst.error_code,
                error_text=worst.error_text,
                rows_returned=bucket[0].rows_returned,
                elapsed_ms=sum(r.elapsed_ms for r in bucket),
                wrapped_sql=bucket[0].wrapped_sql,
            )
        )
    return out


_OUTCOME_RANK = {"fail": 3, "skip": 2, "expected-error-confirmed": 1, "pass": 0}


def _worst_outcome(results: list[Result]) -> Result:
    return max(results, key=lambda r: _OUTCOME_RANK.get(r.outcome, 0))


def _format_badge(sid: str, r: Result) -> str:
    symbol = _BADGE_SYMBOL.get(r.outcome, "?")
    if r.outcome == "pass":
        rows = r.rows_returned if r.rows_returned is not None else 0
        return f"<!-- {symbol} {sid} passed ({rows} rows, {r.elapsed_ms}ms) -->"
    if r.outcome == "expected-error-confirmed":
        return (
            f"<!-- {symbol} {sid} expected-error-confirmed: "
            f"{r.error_code or '(no code)'} -->"
        )
    if r.outcome == "fail":
        return f"<!-- {symbol} {sid} failed: {r.error_code or '(no code)'} -->"
    if r.outcome == "skip":
        return f"<!-- {symbol} {sid} skipped -->"
    return f"<!-- ? {sid} {r.outcome} -->"


# ───────── JSON dump ─────────


def dump_json(results: Iterable[Result], path: Path) -> None:
    """Write a deterministic JSON dump of every Result field.

    Keys are sorted; output uses 2-space indentation and a trailing
    newline so byte-for-byte equality holds across runs.
    """
    payload = [asdict(r) for r in results]
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
