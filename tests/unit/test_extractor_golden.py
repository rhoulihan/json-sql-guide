"""Golden-file test: extractor output against the real guide.

Guards against accidental regressions in parsing behavior. The golden
file (tests/golden/guide_catalog.json) is regenerated any time the
guide is edited and committed — the test just asserts that the current
extractor produces byte-identical output against the same guide source.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validator.extractor import extract_file

GUIDE_PATH = (
    Path(__file__).parent.parent.parent.parent
    / "LinkedIn"
    / "articles"
    / "oracle-sql-json-developer-guide.md"
)
GOLDEN_PATH = Path(__file__).parent.parent / "golden" / "guide_catalog.json"


@pytest.mark.skipif(not GUIDE_PATH.exists(), reason="sibling LinkedIn repo not present")
def test_extractor_matches_golden_catalog_for_real_guide() -> None:
    """Extract the live guide, compare to the checked-in golden JSON."""
    snippets = extract_file(GUIDE_PATH)
    actual = [s.to_dict() for s in snippets]
    expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert actual == expected, (
        "Extractor output diverged from golden. If the guide was intentionally "
        "edited, regenerate with:\n"
        "  uv run validator extract "
        "../LinkedIn/articles/oracle-sql-json-developer-guide.md "
        "-o tests/golden/guide_catalog.json"
    )


@pytest.mark.skipif(not GUIDE_PATH.exists(), reason="sibling LinkedIn repo not present")
def test_real_guide_has_expected_block_count() -> None:
    """Sanity: the guide has 67 SQL blocks as of the snapshot baseline."""
    snippets = extract_file(GUIDE_PATH)
    assert len(snippets) == 67
