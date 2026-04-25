"""Seed: ``user_settings`` table for §8 ``JSON_OBJECTAGG`` examples.

Key/value rows that get aggregated into a JSON config object via
``JSON_OBJECTAGG(setting_name VALUE setting_value)``.
"""

from __future__ import annotations

from typing import Any

_ROWS: list[tuple[int, str, str]] = [
    # (user_id, setting_name, setting_value)
    (42, "theme",    "dark"),
    (42, "language", "en"),
    (42, "timezone", "America/Chicago"),
    (43, "theme",    "light"),
    (43, "language", "ja"),
    (43, "timezone", "Asia/Tokyo"),
    (44, "theme",    "auto"),
    (44, "language", "en-GB"),
    (44, "timezone", "Europe/London"),
]


def load(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.executemany(
            "INSERT INTO user_settings (user_id, setting_name, setting_value) "
            "VALUES (:1, :2, :3)",
            _ROWS,
        )
        conn.commit()
    finally:
        cur.close()
