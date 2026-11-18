"""Unit tests for HTML formatters and InlineKeyboards."""

from bot.formatters import (
    build_alert_message,
    build_copy_all_view,
    build_main_menu,
    build_order_details,
    build_orders_list,
)
from bot.scraper import Order


def _sample_orders(count: int = 7) -> list[Order]:
    orders = []
    for i in range(1, count + 1):
        orders.append(
            Order(
                order_id=f"35169000000000000{i}",
                buyer_name=f"Buyer {i}",
                amount=float(50 + i),
                order_date="10-11-2026",
                order_status="Order Placed",
                return_status="Refund Form Filled" if i % 2 == 0 else "Pending",
                settlement_status="Refund Completed" if i == 2 else "Pending",
                is_return=(i % 2 == 0),
            )
        )
    return orders


def test_build_main_menu():
    """Main menu should include greeting and required buttons."""
    url = "https://script.google.com/test"
    text, markup = build_main_menu(url)

    assert "Welcome to the Orders &amp; Returns Tracker" in text
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    button_texts = [b.text for b in buttons]

    assert "🔗 Open Script" in button_texts
    assert "📦 All Orders" in button_texts
    assert "🔄 Returns Only" in button_texts
    assert "🔄 Refresh Data" in button_texts


def test_build_orders_list_formatting_and_copy_button():
    """List should wrap order ID in <code> and provide CopyTextButton."""
    orders = _sample_orders(3)
    text, markup = build_orders_list(orders, filter_type="all", page=0)

    # Verify <code> tag presence
    assert "<code>351690000000000001</code>" in text

    # Verify CopyTextButton presence
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    copy_buttons = [b for b in buttons if b.copy_text is not None]
    assert len(copy_buttons) == 3
    assert copy_buttons[0].copy_text.text == "351690000000000001"


def test_build_orders_list_pagination():
    """7 orders with page_size=5 should create 2 pages."""
    orders = _sample_orders(7)
    text_p0, markup_p0 = build_orders_list(orders, filter_type="all", page=0)
    assert "Showing 1–5 of 7" in text_p0

    # Next page button should be present
    buttons_p0 = [b.text for row in markup_p0.inline_keyboard for b in row]
    assert "Next ➡️" in buttons_p0
    assert "⬅️ Prev" not in buttons_p0

    # Page 1
    text_p1, markup_p1 = build_orders_list(orders, filter_type="all", page=1)
    assert "Showing 6–7 of 7" in text_p1
    buttons_p1 = [b.text for row in markup_p1.inline_keyboard for b in row]
    assert "⬅️ Prev" in buttons_p1
    assert "Next ➡️" not in buttons_p1


def test_build_copy_all_view():
    """Copy all view should present all IDs in pre tags."""
    orders = _sample_orders(3)
    text, markup = build_copy_all_view(orders, filter_type="all", page=0)
    assert "<pre>" in text
    assert "351690000000000001\n351690000000000002\n351690000000000003" in text
    assert len(markup.inline_keyboard) == 1


def test_build_order_details():
    """Order detail view must format all fields."""
    order = _sample_orders(1)[0]
    text, markup = build_order_details(order, filter_type="all", page=0)
    assert f"<code>{order.order_id}</code>" in text
    assert order.buyer_name in text
    assert f"₹{order.amount:.2f}" in text
    assert len(markup.inline_keyboard) == 2


def test_build_alert_message():
    """Alert message should display new order or update banner with copy button."""
    order = _sample_orders(1)[0]
    text, markup = build_alert_message(order, is_new_order=True)
    assert "NEW ORDER DETECTED" in text
    assert f"<code>{order.order_id}</code>" in text
    buttons = [btn for row in markup.inline_keyboard for btn in row]
    assert any(b.copy_text and b.copy_text.text == order.order_id for b in buttons)
