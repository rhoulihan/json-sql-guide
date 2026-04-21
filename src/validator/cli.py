"""Validator CLI entry point.

Each subcommand is a thin shim over a library function in the matching
module. Keeps the CLI layer test-light — library functions own the
behavior, CLI owns the arg parsing and I/O.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from validator import __version__
from validator.extractor import extract_file


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


if __name__ == "__main__":
    main(prog_name="validator")  # pragma: no cover
    sys.exit(0)  # pragma: no cover
