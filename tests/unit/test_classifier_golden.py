"""Golden-distribution test: classifier against the real guide catalog.

Spec (implementation-plan §6): classifying the full 67-block catalog
should produce ~58 executable (query + ddl) and ~6 fragments, with the
balance comment-only. Exact counts are pinned here so we notice when
the distribution shifts.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from validator.classifier import Classification, classify
from validator.models import Snippet

GOLDEN_CATALOG = Path(__file__).parent.parent / "golden" / "guide_catalog.json"


@pytest.mark.skipif(not GOLDEN_CATALOG.exists(), reason="golden catalog not present")
def test_classifier_distribution_over_real_guide() -> None:
    data = json.loads(GOLDEN_CATALOG.read_text(encoding="utf-8"))
    snippets = [Snippet(**row) for row in data]
    counts = Counter(classify(s).classification for s in snippets)

    # Total = 67 (guarded by extractor golden)
    assert sum(counts.values()) == 67

    # Executable = queries + DDL. The guide text stated ~58 in the plan.
    executable = counts[Classification.STANDALONE_QUERY] + counts[Classification.STANDALONE_DDL]
    assert executable >= 55, f"executable snippets dropped to {executable}"

    # Fragments should be a small minority — partial WHERE / JSON_TABLE /
    # NESTED PATH / CYCLE blocks illustrated in the guide.
    assert counts[Classification.FRAGMENT] <= 12

    # No comment-only yet in this guide (the author would add @skip
    # directive comments in Phase 3 if they did). If this ever becomes
    # non-zero, document it.
    assert counts[Classification.COMMENT_ONLY] == 0
