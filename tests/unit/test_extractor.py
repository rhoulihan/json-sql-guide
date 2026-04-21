"""Tests for the markdown SQL extractor.

The extractor consumes markdown text and emits a deterministic catalog of
every ```sql fenced block with line number, section heading, subsection
heading, and raw body. It does NOT classify, validate, or execute — it's
a pure parser.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

from validator.extractor import (
    Snippet,
    UnclosedFenceError,
    extract,
    extract_file,
)


# ───────── 1 — empty input yields empty catalog ─────────

def test_extractor_returns_empty_catalog_for_markdown_without_sql_fences() -> None:
    md = dedent(
        """\
        # Heading

        Just prose, no code fences at all.

        Some more prose.
        """
    )
    assert extract(md) == []


# ───────── 2 — single block is captured ─────────

def test_extractor_finds_single_sql_block() -> None:
    md = dedent(
        """\
        # Heading

        ```sql
        SELECT 1 FROM DUAL;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].sql == "SELECT 1 FROM DUAL;"


# ───────── 3 — opening fence line number is recorded ─────────

def test_extractor_records_line_number_of_opening_fence() -> None:
    md = "\n".join(
        [
            "# Heading",      # line 1
            "",               # line 2
            "prose here",     # line 3
            "",               # line 4
            "```sql",         # line 5  <- opener
            "SELECT 1;",      # line 6
            "```",            # line 7
        ]
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].line == 5


# ───────── 4 — section from preceding H2 ─────────

def test_extractor_captures_current_section_from_preceding_h2() -> None:
    md = dedent(
        """\
        # Title

        ## 3. JSON_VALUE

        Some prose.

        ```sql
        SELECT JSON_VALUE(d, '$.x') FROM t;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].section == "3. JSON_VALUE"
    assert snippets[0].subsection is None


# ───────── 5 — subsection from preceding H3 ─────────

def test_extractor_captures_current_subsection_from_preceding_h3() -> None:
    md = dedent(
        """\
        ## 3. JSON_VALUE

        ### RETURNING clause

        ```sql
        SELECT JSON_VALUE(d, '$.x' RETURNING NUMBER) FROM t;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].section == "3. JSON_VALUE"
    assert snippets[0].subsection == "RETURNING clause"


# ───────── 6 — H2 transition updates section ─────────

def test_extractor_updates_section_when_a_new_h2_appears() -> None:
    md = dedent(
        """\
        ## Section A

        ```sql
        SELECT 'a' FROM DUAL;
        ```

        ## Section B

        ```sql
        SELECT 'b' FROM DUAL;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 2
    assert snippets[0].section == "Section A"
    assert snippets[1].section == "Section B"
    # Moving into a new H2 clears the previously-set H3 too.
    assert snippets[0].subsection is None
    assert snippets[1].subsection is None


# ───────── 7 — non-SQL fences are ignored ─────────

def test_extractor_ignores_non_sql_fences() -> None:
    md = dedent(
        """\
        ```python
        print("hi")
        ```

        ```json
        {"x": 1}
        ```

        ```
        untagged fence
        ```
        """
    )
    assert extract(md) == []


# ───────── 8 — leading dash comments preserved ─────────

def test_extractor_preserves_leading_dash_comments_inside_block() -> None:
    md = dedent(
        """\
        ```sql
        -- explanatory comment
        SELECT 1 FROM DUAL;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].sql.splitlines()[0] == "-- explanatory comment"
    assert snippets[0].sql.splitlines()[1] == "SELECT 1 FROM DUAL;"


# ───────── 9 — multi-statement block stored as one entry ─────────

def test_extractor_handles_multiple_statements_in_one_block() -> None:
    md = dedent(
        """\
        ```sql
        SELECT 1 FROM DUAL;
        SELECT 2 FROM DUAL;
        ```
        """
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert "SELECT 1" in snippets[0].sql
    assert "SELECT 2" in snippets[0].sql


# ───────── 10 — sequential zero-padded ids ─────────

def test_extractor_assigns_sequential_ids_by_appearance_order() -> None:
    md = dedent(
        """\
        ```sql
        SELECT 'a' FROM DUAL;
        ```

        ```sql
        SELECT 'b' FROM DUAL;
        ```

        ```sql
        SELECT 'c' FROM DUAL;
        ```
        """
    )
    snippets = extract(md)
    assert [s.id for s in snippets] == ["sql-0001", "sql-0002", "sql-0003"]


# ───────── 11 — determinism ─────────

def test_extractor_is_deterministic() -> None:
    md = dedent(
        """\
        ## §

        ```sql
        SELECT 1 FROM DUAL;
        ```

        ### Sub

        ```sql
        SELECT 2 FROM DUAL;
        ```
        """
    )
    first = [s.__dict__ for s in extract(md)]
    second = [s.__dict__ for s in extract(md)]
    assert first == second


# ───────── 12 — line number is opener only ─────────

def test_extractor_uses_only_the_opening_fence_line_for_positioning() -> None:
    md = "\n".join(
        [
            "```sql",           # line 1 — opener
            "SELECT",           # line 2
            "  1",              # line 3
            "FROM DUAL;",       # line 4
            "```",              # line 5 — closer
        ]
    )
    snippets = extract(md)
    assert len(snippets) == 1
    assert snippets[0].line == 1


# ───────── 13 — unclosed fence raises ─────────

def test_extractor_rejects_unclosed_fence_with_clear_error() -> None:
    md = dedent(
        """\
        # Heading

        ```sql
        SELECT 1 FROM DUAL;
        """
    )
    with pytest.raises(UnclosedFenceError) as excinfo:
        extract(md)
    # Error should reference the opening line for the contributor.
    assert "line 3" in str(excinfo.value) or "line=3" in str(excinfo.value)


# ───────── 14 — CLI writes JSON to stdout ─────────

def test_extractor_cli_writes_catalog_to_stdout_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from click.testing import CliRunner

    from validator.cli import main

    source = tmp_path / "guide.md"
    source.write_text(
        dedent(
            """\
            ## A

            ```sql
            SELECT 1 FROM DUAL;
            ```
            """
        )
    )
    runner = CliRunner()
    result = runner.invoke(main, ["extract", str(source)])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["sql"] == "SELECT 1 FROM DUAL;"
    assert data[0]["section"] == "A"
    assert data[0]["id"] == "sql-0001"


# ───────── 15 — CLI writes to file with -o flag ─────────

def test_extractor_cli_writes_to_file_when_output_flag_is_set(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from validator.cli import main

    source = tmp_path / "guide.md"
    source.write_text(
        dedent(
            """\
            ```sql
            SELECT 1 FROM DUAL;
            ```
            """
        )
    )
    out = tmp_path / "catalog.json"
    runner = CliRunner()
    result = runner.invoke(main, ["extract", str(source), "-o", str(out)])
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["sql"] == "SELECT 1 FROM DUAL;"


# ───────── helper — extract_file ─────────

def test_extract_file_reads_from_disk(tmp_path: Path) -> None:
    """Bonus wrapper test — extract_file() is the public thin I/O layer."""
    source = tmp_path / "guide.md"
    source.write_text(
        dedent(
            """\
            ```sql
            SELECT 1 FROM DUAL;
            ```
            """
        )
    )
    snippets = extract_file(source)
    assert len(snippets) == 1
    assert isinstance(snippets[0], Snippet)
