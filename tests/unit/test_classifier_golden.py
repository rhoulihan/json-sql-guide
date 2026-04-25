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

    total = sum(counts.values())
    assert 50 <= total <= 100

    # Executable = queries + DDL. Should be the bulk of the guide.
    executable = counts[Classification.STANDALONE_QUERY] + counts[Classification.STANDALONE_DDL]
    assert executable >= total * 0.7, f"executable snippets dropped to {executable}/{total}"

    # Fragments should be a small minority — partial WHERE / JSON_TABLE /
    # NESTED PATH / CYCLE blocks illustrated in the guide.
    assert counts[Classification.FRAGMENT] <= 15
