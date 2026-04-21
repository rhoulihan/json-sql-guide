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
        "customer": "Lambda LLC",
        "status": "shipped",
        "amount": 100.0,
        "items": [{"sku": "GIZMO-100", "quantity": 1, "unitPrice": 100.0}],
        "shipping": {"method": "ground", "address": {"city": "Remote", "state": "NV"}},
        "tags": [1, "priority", 42, "b2b"],
    },
    {
        "orderId": 2002,
        "customer": "Mu Holdings",
        "status": "shipped",
        "amount": 250.0,
        "items": [{"sku": "GIZMO-250", "quantity": 2, "unitPrice": 125.0}],
        "shipping": {"method": "ground", "address": {"city": "Elsewhere", "state": "TX"}},
        "tags": [100, 200, "research"],
    },
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO orders (order_id, order_doc) VALUES (:1, :2)",
            [(o["orderId"], json.dumps(o)) for o in _ORDERS],
        )
        conn.commit()
    finally:
        cur.close()
