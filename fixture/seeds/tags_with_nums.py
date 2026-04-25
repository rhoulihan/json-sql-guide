"""Seed: orders with mixed numeric + string tags.

Exercises the multivalue index typed-variant examples in §11 — where
the guide shows ``.tags.string()`` and ``.tags.number()`` variants of
the same multivalue index.
"""

from __future__ import annotations

import json
from typing import Any

_ORDERS: list[dict[str, Any]] = [
    {
        "orderId": 2001,
        "customer": {
            "name": "Lambda LLC",
            "tier": "gold",
            "address": {"city": "Remote", "state": "NV", "zip": "89101"},
        },
        "status": "shipped",
        "priority": "normal",
        "orderDate": "2025-04-01",
        "items": [{"product": "Gizmo 100", "quantity": 1, "unitPrice": 100.0, "category": "hardware"}],
        "shipping": {"method": "ground", "address": {"city": "Remote", "state": "NV", "zip": "89101"}},
        "tags": [1, "priority", 42, "b2b"],
    },
    {
        "orderId": 2002,
        "customer": {
            "name": "Mu Holdings",
            "tier": "silver",
            "address": {"city": "Elsewhere", "state": "TX", "zip": "75001"},
        },
        "status": "shipped",
        "priority": "high",
        "orderDate": "2025-04-02",
        "items": [{"product": "Gizmo 250", "quantity": 2, "unitPrice": 125.0, "category": "hardware"}],
        "shipping": {"method": "ground", "address": {"city": "Elsewhere", "state": "TX", "zip": "75001"}},
        "tags": [100, 200, "research"],
    },
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO orders (order_doc) VALUES (:1)",
            [(json.dumps(o),) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
