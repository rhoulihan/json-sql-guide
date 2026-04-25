"""Seed: ``legacy_table`` — CLOB-backed JSON for the §9 migration story.

The guide uses ``legacy_table`` to illustrate moving from CLOB-stored
JSON (``IS JSON`` check constraint) to native ``JSON`` storage.
"""

from __future__ import annotations

import json
from typing import Any

_ROWS: list[dict[str, Any]] = [
    {"id": 1, "kind": "customer", "name": "Legacy Co", "active": True},
    {"id": 2, "kind": "customer", "name": "Old Systems Inc", "active": False},
    {"id": 3, "kind": "vendor", "name": "Heritage Supply", "active": True},
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO legacy_table (id, legacy_text_column) VALUES (:1, :2)",
            [(r["id"], json.dumps(r)) for r in _ROWS],
        )
        conn.commit()
    finally:
        cur.close()
