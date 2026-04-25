"""Validator CLI entry point.

Each subcommand is a thin shim over a library function in the matching
module. Keeps the CLI layer test-light — library functions own the
behavior, CLI owns the arg parsing and I/O.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click
from rich.console import Console

from validator import __version__
from validator.diff import diff_exit_code, diff_results, render_diff_md
from validator.directives import apply_directives, load_sidecar
from validator.extractor import extract_file
from validator.fixture import FixtureLoader
from validator.reporter import (
    dump_json,
    render_annotated,
    render_cli,
    render_junit,
)
from validator.runner import Result, Runner


@click.group(help="Validator for the Oracle SQL/JSON Developer Guide.")
@click.version_option(__version__, prog_name="validator")
def main() -> None:
    """CLI group."""


@main.command(help="Extract every ```sql block from a markdown guide into a catalog JSON.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write catalog to FILE. If omitted, catalog is printed to stdout.",
)
def extract(source: Path, output: Path | None) -> None:
    """Run the extractor and emit the catalog as JSON."""
    snippets = extract_file(source)
    payload = json.dumps([s.to_dict() for s in snippets], indent=2, ensure_ascii=False)

    if output is None:
        click.echo(payload)
    else:
        output.write_text(payload + "\n", encoding="utf-8")


@main.command(help="Run the validator end-to-end against a guide markdown.")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("reports"),
    help="Directory to write junit.xml, results.json, annotated MD.",
)
@click.option("--fast-fail", is_flag=True, help="Stop on first failure.")
@click.option(
    "--overrides",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("docs/sql-overrides.yaml"),
    help="Sidecar YAML with per-snippet directives. Skipped if missing.",
)
@click.option(
    "--fixture-profile",
    "fixture_profiles",
    multiple=True,
    default=(
        "base",
        "tags_with_nums",
        "deep_nest",
        "dates_and_intervals",
        "hybrid",
        "events",
        "user_settings",
        "legacy",
    ),
    help="Seed profiles to load before running. Repeatable. Pass once with empty value to skip fixture load.",
)
def run(
    source: Path,
    out_dir: Path,
    fast_fail: bool,
    overrides: Path,
    fixture_profiles: tuple[str, ...],
) -> None:
    """Extract → direct → execute → report."""
    out_dir.mkdir(parents=True, exist_ok=True)

    snippets = extract_file(source)
    sidecar = load_sidecar(overrides)
    directed = [apply_directives(s, sidecar_overrides=sidecar) for s in snippets]

    conn_factory = _make_oracle_factory()

    profiles = [p for p in fixture_profiles if p]
    if profiles:
        loader_conn = conn_factory("default")
        FixtureLoader(loader_conn, profiles=list(profiles)).load()

    runner = Runner(
        conn_factory,
        options=_runner_options(fast_fail=fast_fail),
    )
    results = runner.execute(directed)

    junit_path = out_dir / "junit.xml"
    json_path = out_dir / "results.json"
    annotated_path = out_dir / "annotated.md"
    render_junit(results, junit_path)
    dump_json(results, json_path)
    render_annotated(results, source, annotated_path)

    console = Console()
    render_cli(results, console)

    failed = sum(1 for r in results if r.outcome == "fail")
    sys.exit(1 if failed else 0)


@main.command(name="diff", help="Diff two results.json files; emit markdown.")
@click.argument("previous", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("current", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["md", "json"], case_sensitive=False),
    default="md",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write diff to FILE. If omitted, prints to stdout.",
)
def diff_cmd(
    previous: Path, current: Path, output_format: str, output: Path | None
) -> None:
    """Compare two results.json runs and emit a regression report."""
    prev = _load_results(previous)
    curr = _load_results(current)
    diff = diff_results(prev, curr)

    if output_format.lower() == "md":
        body = render_diff_md(diff)
    else:
        body = json.dumps(
            {
                "regressions": [_change_to_dict(c) for c in diff.regressions],
                "improvements": [_change_to_dict(c) for c in diff.improvements],
                "newly_skipped": [_change_to_dict(c) for c in diff.newly_skipped],
                "newly_added": [asdict(r) for r in diff.newly_added],
                "removed": [asdict(r) for r in diff.removed],
                "unchanged_count": diff.unchanged_count,
            },
            indent=2,
        )

    if output is None:
        click.echo(body)
    else:
        output.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")

    sys.exit(diff_exit_code(diff))


# ───────── helpers ─────────


def _runner_options(*, fast_fail: bool) -> Any:
    from validator.runner import RunnerOptions

    return RunnerOptions(fast_fail=fast_fail)


def _make_oracle_factory() -> Any:
    """Return a factory that lazily opens Oracle connections per role.

    Reads ORACLE_HOST/PORT/SERVICE/USER/PASSWORD from the environment.
    DBA credentials default to the same user when not set.
    """
    import oracledb

    host = os.environ.get("ORACLE_HOST", "localhost")
    port = int(os.environ.get("ORACLE_PORT", "1521"))
    service = os.environ.get("ORACLE_SERVICE", "FREEPDB1")
    user = os.environ.get("ORACLE_USER", "validator")
    password = os.environ.get("ORACLE_PASSWORD", "validator")
    dba_user = os.environ.get("ORACLE_DBA_USER", user)
    dba_password = os.environ.get("ORACLE_DBA_PASSWORD", password)
    dsn = f"{host}:{port}/{service}"

    def factory(role: str) -> Any:
        if role == "dba":
            return oracledb.connect(user=dba_user, password=dba_password, dsn=dsn)
        return oracledb.connect(user=user, password=password, dsn=dsn)

    return factory


def _load_results(path: Path) -> list[Result]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [Result(**record) for record in payload]


def _change_to_dict(c: Any) -> dict[str, Any]:
    return {
        "id": c.id,
        "line": c.line,
        "previous": asdict(c.previous),
        "current": asdict(c.current),
    }


if __name__ == "__main__":
    main(prog_name="validator")  # pragma: no cover
    sys.exit(0)  # pragma: no cover
