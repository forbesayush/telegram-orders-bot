"""Unit tests for SQLite storage layer."""

import tempfile
from pathlib import Path

import pytest

from bot.storage import Storage


@pytest.fixture
def temp_storage():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    storage = Storage(db_path)
    yield storage
    Path(db_path).unlink(missing_ok=True)


def test_record_new_order(temp_storage: Storage):
    """Recording a new order should return (is_new=True, is_changed=False)."""
    order = {
        "order_id": "351692994041939520",
        "buyer_name": "Raina Tapadar",
        "amount": 58.0,
        "order_date": "10-11-2026",
        "order_status": "Order Placed",
        "return_status": "Pending",
        "settlement_status": "Pending",
    }
    is_new, is_changed = temp_storage.record_order(order)
    assert is_new is True
    assert is_changed is False

    retrieved = temp_storage.get_order("351692994041939520")
    assert retrieved is not None
    assert retrieved["buyer_name"] == "Raina Tapadar"
    assert retrieved["amount"] == 58.0


def test_update_order_status_change(temp_storage: Storage):
    """Updating an existing order with changed status should return (False, True)."""
    order = {
        "order_id": "351692994041939520",
        "buyer_name": "Raina Tapadar",
        "amount": 58.0,
        "order_date": "10-11-2026",
        "order_status": "Order Placed",
        "return_status": "Pending",
        "settlement_status": "Pending",
    }
    temp_storage.record_order(order)

    # Status changes to Refund Form Filled
    updated = dict(order)
    updated["return_status"] = "Refund Form Filled"
    is_new, is_changed = temp_storage.record_order(updated)
    assert is_new is False
    assert is_changed is True

    retrieved = temp_storage.get_order("351692994041939520")
    assert retrieved["return_status"] == "Refund Form Filled"


def test_get_all_orders_and_ids(temp_storage: Storage):
    """Test retrieving lists of all orders and order IDs."""
    o1 = {"order_id": "111", "buyer_name": "Alice", "amount": 10.0}
    o2 = {"order_id": "222", "buyer_name": "Bob", "amount": 20.0}
    temp_storage.record_order(o1)
    temp_storage.record_order(o2)

    ids = temp_storage.get_all_order_ids()
    assert "111" in ids
    assert "222" in ids
    assert temp_storage.count_orders() == 2
