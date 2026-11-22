"""Storage layer for the Telegram Orders Bot.

Stores discovered orders and return states in a local SQLite database,
supporting deduplication and auto-alert change detection.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class Storage:
    """SQLite-backed persistent store for orders and return statuses."""

    def __init__(self, db_path: str = "orders.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for SQLite connections with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    buyer_name TEXT,
                    amount REAL DEFAULT 0.0,
                    order_date TEXT,
                    order_status TEXT,
                    return_status TEXT,
                    settlement_status TEXT,
                    first_seen_at TEXT NOT NULL,
                    last_updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_orders_return_status
                ON orders (return_status)
                """
            )

    def record_order(self, order: dict[str, Any]) -> tuple[bool, bool]:
        """Record or update an order.

        Returns:
            (is_new_order, is_status_changed)
            - is_new_order: True if the order ID was never seen before.
            - is_status_changed: True if return or settlement status changed.
        """
        order_id = str(order.get("order_id", "")).strip()
        if not order_id:
            return False, False

        buyer_name = order.get("buyer_name", "")
        amount = float(order.get("amount") or 0.0)
        order_date = order.get("order_date", "")
        order_status = order.get("order_status", "")
        return_status = order.get("return_status", "")
        settlement_status = order.get("settlement_status", "")
        now_iso = datetime.now(UTC).isoformat()

        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT return_status, settlement_status FROM orders WHERE order_id = ?",
                (order_id,),
            )
            existing = cursor.fetchone()

            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO orders (
                        order_id, buyer_name, amount, order_date,
                        order_status, return_status, settlement_status,
                        first_seen_at, last_updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        buyer_name,
                        amount,
                        order_date,
                        order_status,
                        return_status,
                        settlement_status,
                        now_iso,
                        now_iso,
                    ),
                )
                return True, False

            # Existing order: check if return or settlement status changed
            old_return = existing["return_status"]
            old_settle = existing["settlement_status"]
            changed = (old_return != return_status) or (old_settle != settlement_status)

            cursor.execute(
                """
                UPDATE orders SET
                    buyer_name = ?,
                    amount = ?,
                    order_date = ?,
                    order_status = ?,
                    return_status = ?,
                    settlement_status = ?,
                    last_updated_at = ?
                WHERE order_id = ?
                """,
                (
                    buyer_name,
                    amount,
                    order_date,
                    order_status,
                    return_status,
                    settlement_status,
                    now_iso,
                    order_id,
                ),
            )
            return False, changed

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """Fetch a single order by its ID."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders WHERE order_id = ?", (str(order_id),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_orders(self) -> list[dict[str, Any]]:
        """Fetch all recorded orders."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orders ORDER BY order_date DESC, order_id ASC")
            return [dict(row) for row in cursor.fetchall()]

    def get_all_order_ids(self) -> list[str]:
        """Return a list of all known order IDs."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT order_id FROM orders ORDER BY order_id ASC")
            return [row["order_id"] for row in cursor.fetchall()]

    def count_orders(self) -> int:
        """Count total stored orders."""
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM orders")
            return int(cursor.fetchone()[0])
