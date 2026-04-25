"""Outcome diffing — compare two Result lists and surface changes.

A *regression* is a snippet that was succeeding (``pass`` or
``expected-error-confirmed``) and is now failing. An *improvement* is
the inverse — a snippet that was failing and is now succeeding.
``elapsed_ms`` fluctuations are ignored: only outcome and error_code
changes count.

The CLI uses :func:`diff_exit_code` so CI can mark a build red on
regressions even when the absolute pass/fail counts look fine.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from validator.runner import Result

__all__ = [
    "ResultChange",
    "ResultDiff",
    "diff_exit_code",
    "diff_results",
    "render_diff_md",
]

_SUCCESS_OUTCOMES = frozenset({"pass", "expected-error-confirmed"})


@dataclass(frozen=True, slots=True)
class ResultChange:
    """One snippet whose outcome flipped between runs."""

    id: str
    line: int
    previous: Result
    current: Result


@dataclass(frozen=True, slots=True)
class ResultDiff:
    """Structured diff between two Result lists."""

    regressions: list[ResultChange] = field(default_factory=list)
    improvements: list[ResultChange] = field(default_factory=list)
    newly_skipped: list[ResultChange] = field(default_factory=list)
    newly_added: list[Result] = field(default_factory=list)
    removed: list[Result] = field(default_factory=list)
    unchanged_count: int = 0


def diff_results(prev: Iterable[Result], curr: Iterable[Result]) -> ResultDiff:
    """Compare *prev* and *curr* by ``id``.

    A snippet's outcome change is treated as semantically meaningful;
    ``elapsed_ms`` and other timing-style fields are ignored. Snippets
    only present in one list show up under ``newly_added`` or
    ``removed``.
    """
    prev_by_id = {r.id: r for r in prev}
    curr_by_id = {r.id: r for r in curr}

    regressions: list[ResultChange] = []
    improvements: list[ResultChange] = []
    newly_skipped: list[ResultChange] = []
    newly_added: list[Result] = []
    removed: list[Result] = []
    unchanged = 0

    for sid, current in curr_by_id.items():
        previous = prev_by_id.get(sid)
        if previous is None:
            newly_added.append(current)
            continue

        if not _outcome_changed(previous, current):
            unchanged += 1
            continue

        change = ResultChange(id=sid, line=current.line, previous=previous, current=current)
        prev_success = previous.outcome in _SUCCESS_OUTCOMES
        curr_success = current.outcome in _SUCCESS_OUTCOMES

        if prev_success and current.outcome == "fail":
            regressions.append(change)
        elif previous.outcome == "fail" and curr_success:
            improvements.append(change)
        elif previous.outcome != "skip" and current.outcome == "skip":
            newly_skipped.append(change)
        else:
            # Other outcome flips (e.g. skip → pass) are improvements
            # if the new outcome is a success.
            if curr_success:
                improvements.append(change)
            else:
                regressions.append(change)

    for sid, previous in prev_by_id.items():
        if sid not in curr_by_id:
            removed.append(previous)

    return ResultDiff(
        regressions=regressions,
        improvements=improvements,
        newly_skipped=newly_skipped,
        newly_added=newly_added,
        removed=removed,
        unchanged_count=unchanged,
    )


def _outcome_changed(prev: Result, curr: Result) -> bool:
    """Return True iff the semantic outcome changed.

    Ignores ``elapsed_ms``, ``rows_returned``, ``wrapped_sql`` — those
    fluctuate run-to-run without being a real regression.
    """
    if prev.outcome != curr.outcome:
        return True
    return prev.outcome == "fail" and prev.error_code != curr.error_code


def diff_exit_code(diff: ResultDiff) -> int:
    """Return ``1`` if *diff* contains any regressions, else ``0``."""
    return 1 if diff.regressions else 0


def render_diff_md(diff: ResultDiff) -> str:
    """Render *diff* as Markdown with one H2 section per category."""
    lines: list[str] = []
    lines.append("# Validator Diff")
    lines.append("")
    lines.append(f"Unchanged: {diff.unchanged_count}")
    lines.append("")

    lines.append("## Regressions")
    if not diff.regressions:
        lines.append("_None._")
    else:
        for c in diff.regressions:
            code = c.current.error_code or "(no code)"
            lines.append(
                f"- `{c.id}` (line {c.line}): "
                f"{c.previous.outcome} → {c.current.outcome} ({code})"
            )
    lines.append("")

    lines.append("## Improvements")
    if not diff.improvements:
        lines.append("_None._")
    else:
        for c in diff.improvements:
            lines.append(
                f"- `{c.id}` (line {c.line}): "
                f"{c.previous.outcome} → {c.current.outcome}"
            )
    lines.append("")

    lines.append("## Newly Skipped")
    if not diff.newly_skipped:
        lines.append("_None._")
    else:
        for c in diff.newly_skipped:
            lines.append(f"- `{c.id}` (line {c.line}): now skipped")
    lines.append("")

    lines.append("## Added")
    if not diff.newly_added:
        lines.append("_None._")
    else:
        for r in diff.newly_added:
            lines.append(f"- `{r.id}` (line {r.line}): {r.outcome}")
    lines.append("")

    lines.append("## Removed")
    if not diff.removed:
        lines.append("_None._")
    else:
        for r in diff.removed:
            lines.append(f"- `{r.id}` (line {r.line})")

    return "\n".join(lines) + "\n"
