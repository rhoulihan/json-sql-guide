"""Seed: append-only events table for §3 / §4 examples.

The guide's narrative uses an ``events`` table to illustrate JSON
querying over an event log (action types, timestamps, contextual
payloads). Documents share a common shape so JSON_VALUE projections
demonstrate consistently.
"""

from __future__ import annotations

import json
from typing import Any

_EVENTS: list[dict[str, Any]] = [
    {
        "eventId": 5001,
        "eventType": "order.placed",
        "occurredAt": "2026-02-01T09:14:22Z",
        "actor": {"type": "customer", "id": "CUST-001"},
        "payload": {"orderId": 1001, "amount": 1299.00},
    },
    {
        "eventId": 5002,
        "eventType": "order.shipped",
        "occurredAt": "2026-02-01T15:42:00Z",
        "actor": {"type": "system", "id": "warehouse-east"},
        "payload": {"orderId": 1001, "tracking": "1Z999AA10123456784"},
    },
    {
        "eventId": 5003,
        "eventType": "payment.received",
        "occurredAt": "2026-02-02T08:01:11Z",
        "actor": {"type": "system", "id": "payments-gateway"},
        "payload": {"orderId": 1002, "amount": 58.50, "method": "card"},
    },
    {
        "eventId": 5004,
        "eventType": "user.login",
        "occurredAt": "2026-02-02T11:20:30Z",
        "actor": {"type": "user", "id": "USR-101"},
        "payload": {"ip": "192.0.2.45", "userAgent": "Mozilla/5.0"},
    },
    {
        "eventId": 5005,
        "eventType": "order.cancelled",
        "occurredAt": "2026-02-03T14:00:00Z",
        "actor": {"type": "customer", "id": "CUST-004"},
        "payload": {"orderId": 1004, "reason": "duplicate-order"},
    },
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO events (event_doc) VALUES (:1)",
            [(json.dumps(e),) for e in _EVENTS],
        )
        conn.commit()
    finally:
        cur.close()
