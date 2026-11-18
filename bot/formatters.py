"""HTML message builders and InlineKeyboardMarkup constructors.

Follows Bot API 7.11+ CopyTextButton standards and ensures all Order IDs
are wrapped in <code> tags for one-tap copying.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from telegram import CopyTextButton, InlineKeyboardButton, InlineKeyboardMarkup

from bot.scraper import Order

PAGE_SIZE = 5


def build_main_menu(script_url: str) -> tuple[str, InlineKeyboardMarkup]:
    """Build the greeting text and inline keyboard for the main screen."""
    text = (
        "👋 <b>Welcome to the Orders &amp; Returns Tracker</b>\n\n"
        "Monitor live customer orders, refund submissions, and settlement "
        "progress fetched directly from the master Google Apps Script portal.\n\n"
        "<i>Select an option below to get started:</i>"
    )

    keyboard = [
        [InlineKeyboardButton("🔗 Open Script", url=script_url)],
        [
            InlineKeyboardButton("📦 All Orders", callback_data="orders:all:0"),
            InlineKeyboardButton("🔄 Returns Only", callback_data="orders:returns:0"),
        ],
        [InlineKeyboardButton("🔄 Refresh Data", callback_data="refresh")],
    ]

    return text, InlineKeyboardMarkup(keyboard)


def build_orders_list(
    orders: Sequence[Order],
    filter_type: str = "all",
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """Build a paginated view of orders with inline copy buttons."""
    total_orders = len(orders)
    total_pages = max(1, math.ceil(total_orders / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))

    start_idx = page * PAGE_SIZE
    end_idx = min(start_idx + PAGE_SIZE, total_orders)
    page_orders = orders[start_idx:end_idx]

    title = "📦 <b>All Orders</b>" if filter_type == "all" else "🔄 <b>Returns Only</b>"

    if not orders:
        empty_text = (
            f"{title}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>No orders found matching the filter.</i>"
        )
        empty_kb = [[InlineKeyboardButton("🔙 Back", callback_data="menu")]]
        return empty_text, InlineKeyboardMarkup(empty_kb)

    lines: list[str] = [
        f"{title} (Showing {start_idx + 1}–{end_idx} of {total_orders})",
        "━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    keyboard: list[list[InlineKeyboardButton]] = []

    for idx, order in enumerate(page_orders, start=start_idx + 1):
        form_icon = "✅" if order.return_status == "Refund Form Filled" else "⏳"
        settle_icon = "✅" if order.settlement_status == "Refund Completed" else "⏳"

        order_block = (
            f"<b>{idx}. Order ID:</b> <code>{order.order_id}</code>\n"
            f"<b>👤 Customer:</b> {order.buyer_name}\n"
            f"<b>💰 Amount:</b> ₹{order.amount:.2f}\n"
            f"<b>📅 Date:</b> {order.order_date}\n"
            f"<b>📋 Status:</b> {order.order_status}\n"
            f"<b>🔄 Refund Form:</b> {form_icon} {order.return_status}\n"
            f"<b>💳 Settlement:</b> {settle_icon} {order.settlement_status}\n"
        )
        lines.append(order_block)

        # Inline button row under each order for instant one-tap copy and details
        btn_copy = InlineKeyboardButton(
            text=f"📋 Copy {order.order_id[-6:]}",
            copy_text=CopyTextButton(text=order.order_id),
        )
        btn_detail = InlineKeyboardButton(
            text=f"🔍 Details #{idx}",
            callback_data=f"detail:{order.order_id}:{filter_type}:{page}",
        )
        keyboard.append([btn_copy, btn_detail])

    message_text = "\n".join(lines)

    # Pagination navigation controls
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("⬅️ Prev", callback_data=f"orders:{filter_type}:{page - 1}")
        )
    nav_row.append(
        InlineKeyboardButton(
            f"📄 {page + 1}/{total_pages}",
            callback_data=f"noop:{page}",
        )
    )
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("Next ➡️", callback_data=f"orders:{filter_type}:{page + 1}")
        )

    keyboard.append(nav_row)

    # Bottom action buttons
    bottom_row = [
        InlineKeyboardButton(
            "📋 Copy All IDs",
            callback_data=f"copy_all:{filter_type}:{page}",
        ),
        InlineKeyboardButton("🔙 Back", callback_data="menu"),
    ]
    keyboard.append(bottom_row)

    return message_text, InlineKeyboardMarkup(keyboard)


def build_order_details(
    order: Order,
    filter_type: str = "all",
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """Build a detailed view for a single order."""
    form_icon = "✅" if order.return_status == "Refund Form Filled" else "⏳"
    settle_icon = "✅" if order.settlement_status == "Refund Completed" else "⏳"

    text = (
        "🔍 <b>Detailed Order Information</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>🆔 Order ID:</b> <code>{order.order_id}</code>\n"
        f"<b>👤 Customer (Sold To):</b> {order.buyer_name}\n"
        f"<b>💰 Order Amount:</b> ₹{order.amount:.2f}\n"
        f"<b>📅 Order Date:</b> {order.order_date}\n\n"
        f"<b>📊 Progress Milestones:</b>\n"
        f"• Step 1 (Order Confirmation): ✅ {order.order_status}\n"
        f"• Step 2 (Refund Form): {form_icon} {order.return_status}\n"
        f"• Step 3 (Final Settlement): {settle_icon} {order.settlement_status}\n\n"
        f"<b>🔄 Is Return / Refund Case:</b> {'Yes' if order.is_return else 'No'}\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📋 Copy Order ID",
                copy_text=CopyTextButton(text=order.order_id),
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 Back to List",
                callback_data=f"orders:{filter_type}:{page}",
            )
        ],
    ]

    return text, InlineKeyboardMarkup(keyboard)


def build_copy_all_view(
    orders: Sequence[Order],
    filter_type: str = "all",
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    """Display all order IDs in a single preformatted block for easy copying."""
    ids_block = "\n".join(order.order_id for order in orders)
    total = len(orders)

    text = (
        f"📋 <b>All Order IDs ({total} Total)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Tap the block below to copy all IDs:</i>\n\n"
        f"<pre>{ids_block}</pre>"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🔙 Back to List",
                callback_data=f"orders:{filter_type}:{page}",
            )
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)


def build_alert_message(order: Order, is_new_order: bool) -> tuple[str, InlineKeyboardMarkup]:
    """Build an automatic alert message for a new order or return status update."""
    header = (
        "🚨 <b>NEW ORDER DETECTED</b>"
        if is_new_order
        else "⚠️ <b>ORDER RETURN / SETTLEMENT UPDATE</b>"
    )

    text = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 Order ID:</b> <code>{order.order_id}</code>\n"
        f"<b>👤 Customer:</b> {order.buyer_name}\n"
        f"<b>💰 Amount:</b> ₹{order.amount:.2f}\n"
        f"<b>📅 Date:</b> {order.order_date}\n"
        f"<b>🔄 Refund Form:</b> {order.return_status}\n"
        f"<b>💳 Settlement:</b> {order.settlement_status}\n"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📋 Copy ID",
                copy_text=CopyTextButton(text=order.order_id),
            )
        ]
    ]

    return text, InlineKeyboardMarkup(keyboard)
