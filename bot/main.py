"""Main entry point and Telegram bot handler setup.

Provides a 100% button-driven interface with zero slash commands,
pagination, inline copying, allowlist gating, and auto-alert polling.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.config import Config
from bot.formatters import (
    build_alert_message,
    build_batch_orders_result,
    build_copy_all_view,
    build_main_menu,
    build_order_details,
    build_orders_list,
    build_single_order_result,
)
from bot.scraper import Order, Scraper
from bot.storage import Storage

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("telegram_orders_bot")


def _is_authorized(user_id: int, allowed_ids: set[int]) -> bool:
    """Check if the user is authorized to use the bot."""
    if not allowed_ids:
        return True
    return user_id in allowed_ids


def _extract_order_ids(text: str) -> list[str]:
    """Extract distinct order IDs from user message text."""
    matches = re.findall(r"\b\d{10,25}\b", text)
    if not matches:
        clean = text.strip()
        if clean and not clean.startswith("/") and clean.lower() not in ("start", "help", "menu", "hi", "hello"):
            tokens = [t.strip() for t in re.split(r"[\s,;]+", clean) if t.strip()]
            for token in tokens:
                if len(token) >= 8 and any(c.isdigit() for c in token):
                    matches.append(token)

    seen: set[str] = set()
    result: list[str] = []
    for oid in matches:
        if oid not in seen:
            seen.add(oid)
            result.append(oid)
    return result


async def generic_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming user messages: check order IDs if present, or show main menu."""
    if not update.effective_user or not update.effective_message:
        return

    user_id = update.effective_user.id
    config: Config = context.bot_data["config"]
    scraper: Scraper = context.bot_data["scraper"]
    storage: Storage = context.bot_data["storage"]

    if not _is_authorized(user_id, config.allowed_user_ids):
        logger.warning("Unauthorized access attempt by user_id=%d", user_id)
        await update.effective_message.reply_text(
            "⛔ <b>Access Denied</b>\n\nYou are not authorized to use this bot.",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_text = (update.effective_message.text or "").strip()
    order_ids = _extract_order_ids(raw_text)

    # If no order IDs detected, display standard main menu
    if not order_ids:
        text, markup = build_main_menu(config.script_url)
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        return

    # Case 1: Single Order ID lookup
    if len(order_ids) == 1:
        oid = order_ids[0]
        status_msg = await update.effective_message.reply_text(
            f"🔍 <i>Checking order <code>{oid}</code> in Google Apps Script...</i>",
            parse_mode=ParseMode.HTML,
        )
        try:
            order = await scraper.fetch_order_direct(oid)
            if order:
                storage.record_order(order.to_dict())

            text, markup = build_single_order_result(order, oid)
            await status_msg.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception as err:
            logger.exception("Error querying single order %s", oid)
            await status_msg.edit_text(
                f"⚠️ <b>Error querying Google Apps Script:</b>\n<code>{err}</code>",
                parse_mode=ParseMode.HTML,
            )
        return

    # Case 2: Batch / Bulk Order IDs lookup
    total = len(order_ids)
    status_msg = await update.effective_message.reply_text(
        f"⏳ <i>Checking <b>{total}</b> orders in Google Apps Script in parallel...</i>",
        parse_mode=ParseMode.HTML,
    )
    try:
        results = await scraper.fetch_orders_batch(order_ids, concurrency=8)
        for ord_obj in results.values():
            if ord_obj:
                storage.record_order(ord_obj.to_dict())

        messages = build_batch_orders_result(results)
        if messages:
            first_text, first_markup = messages[0]
            await status_msg.edit_text(first_text, reply_markup=first_markup, parse_mode=ParseMode.HTML)
            for next_text, next_markup in messages[1:]:
                await update.effective_message.reply_text(
                    next_text, reply_markup=next_markup, parse_mode=ParseMode.HTML
                )
    except Exception as err:
        logger.exception("Error in batch query")
        await status_msg.edit_text(
            f"⚠️ <b>Error during batch query:</b>\n<code>{err}</code>",
            parse_mode=ParseMode.HTML,
        )


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback queries from inline buttons to their respective views."""
    query = update.callback_query
    if not query or not query.data:
        return

    user_id = query.from_user.id
    config: Config = context.bot_data["config"]
    scraper: Scraper = context.bot_data["scraper"]
    storage: Storage = context.bot_data["storage"]

    if not _is_authorized(user_id, config.allowed_user_ids):
        await query.answer("Access denied.", show_alert=True)
        return

    data = query.data

    try:
        # 1. Main menu
        if data == "menu":
            await query.answer()
            text, markup = build_main_menu(config.script_url)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            return

        # 2. Page indicator noop
        if data.startswith("noop:"):
            await query.answer()
            return

        # 3. Refresh data
        if data == "refresh":
            await query.answer("Refreshing data from portal...", show_alert=False)
            orders = await scraper.fetch_all_orders(force_refresh=True)
            for o in orders:
                storage.record_order(o.to_dict())
            text, markup = build_main_menu(config.script_url)
            await query.edit_message_text(
                f"✅ <i>Data refreshed successfully ({len(orders)} orders loaded).</i>\n\n" + text,
                reply_markup=markup,
                parse_mode=ParseMode.HTML,
            )
            return

        # 4. Order list view: "orders:<all|returns>:<page>"
        if data.startswith("orders:"):
            parts = data.split(":")
            filter_type = parts[1] if len(parts) > 1 else "all"
            page = int(parts[2]) if len(parts) > 2 else 0

            await query.answer()
            all_orders = await scraper.fetch_all_orders(force_refresh=False)
            for o in all_orders:
                storage.record_order(o.to_dict())

            if filter_type == "returns":
                filtered = [o for o in all_orders if o.is_return]
            else:
                filtered = all_orders

            text, markup = build_orders_list(filtered, filter_type=filter_type, page=page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            return

        # 5. Order details view: "detail:<order_id>:<filter_type>:<page>"
        if data.startswith("detail:"):
            parts = data.split(":")
            order_id = parts[1]
            filter_type = parts[2] if len(parts) > 2 else "all"
            page = int(parts[3]) if len(parts) > 3 else 0

            await query.answer()
            stored = storage.get_order(order_id)
            if not stored:
                fetched = await scraper.fetch_order_direct(order_id)
                if fetched:
                    stored = fetched.to_dict()
                    storage.record_order(stored)

            if not stored:
                await query.edit_message_text(
                    f"❌ <b>Order {order_id} not found.</b>",
                    parse_mode=ParseMode.HTML,
                )
                return

            order_obj = Order(
                order_id=stored["order_id"],
                buyer_name=stored["buyer_name"],
                amount=stored["amount"],
                order_date=stored["order_date"],
                order_status=stored["order_status"],
                return_status=stored["return_status"],
                settlement_status=stored["settlement_status"],
                is_return="return" in stored["return_status"].lower()
                or stored["return_status"] == "Refund Form Filled",
            )
            text, markup = build_order_details(order_obj, filter_type=filter_type, page=page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            return

        # 6. Copy All IDs: "copy_all:<filter_type>:<page>"
        if data.startswith("copy_all:"):
            parts = data.split(":")
            filter_type = parts[1] if len(parts) > 1 else "all"
            page = int(parts[2]) if len(parts) > 2 else 0

            await query.answer()
            all_orders = await scraper.fetch_all_orders(force_refresh=False)
            if filter_type == "returns":
                target_orders = [o for o in all_orders if o.is_return]
            else:
                target_orders = all_orders

            text, markup = build_copy_all_view(target_orders, filter_type=filter_type, page=page)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            return

    except Exception:
        logger.exception("Error handling callback query")
        await query.answer("An error occurred while loading data.", show_alert=True)


async def alert_poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Background polling job to discover new orders and broadcast change alerts."""
    config: Config = context.bot_data["config"]
    if not config.alert_chat_id:
        return

    scraper: Scraper = context.bot_data["scraper"]
    storage: Storage = context.bot_data["storage"]

    logger.debug("Executing scheduled alert poll job...")
    try:
        orders = await scraper.fetch_all_orders(force_refresh=True)
        for order in orders:
            is_new, is_changed = storage.record_order(order.to_dict())
            if is_new or is_changed:
                logger.info(
                    "Alert trigger for order %s (new=%s, changed=%s)",
                    order.order_id,
                    is_new,
                    is_changed,
                )
                text, markup = build_alert_message(order, is_new_order=is_new)
                try:
                    await context.bot.send_message(
                        chat_id=config.alert_chat_id,
                        text=text,
                        reply_markup=markup,
                        parse_mode=ParseMode.HTML,
                    )
                except Exception as send_err:  # noqa: BLE001
                    logger.error("Failed to deliver alert message to %d: %s", config.alert_chat_id, send_err)
    except Exception as exc:  # noqa: BLE001
        logger.error("Error in alert_poll_job: %s", exc)


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all error handler for uncaught exceptions."""
    logger.error("Exception while handling an update: %s", context.error, exc_info=context.error)


async def _start_health_server(port: int) -> None:
    """Start a lightweight HTTP server for Render/cloud platform health checks."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.read(1024)
            response = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/plain; charset=utf-8\r\n"
                b"Content-Length: 2\r\n"
                b"Connection: close\r\n\r\n"
                b"OK"
            )
            writer.write(response)
            await writer.drain()
        except (ConnectionResetError, BrokenPipeError, TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionResetError, BrokenPipeError, TimeoutError):
                pass

    try:
        server = await asyncio.start_server(handle_client, "0.0.0.0", port)
        logger.info("Cloud health check server listening on 0.0.0.0:%d", port)
        asyncio.create_task(server.serve_forever())
    except Exception as exc:  # noqa: BLE001
        logger.error("Could not bind health server on port %d: %s", port, exc)


async def _on_post_init(app: Application) -> None:
    """Post initialization hook to start health check server if PORT is set."""
    port_env = os.getenv("PORT")
    if port_env:
        try:
            port = int(port_env)
            await _start_health_server(port)
        except ValueError:
            logger.warning("Invalid PORT environment variable: %s", port_env)


def create_application(config: Config) -> Application:
    """Factory to construct and configure the telegram.ext Application."""
    storage = Storage(config.database_path)
    scraper = Scraper(
        script_url=config.script_url,
        seed_order_ids=config.seed_order_ids,
        cache_ttl=config.cache_ttl_seconds,
        timeout=config.http_timeout,
    )

    app = ApplicationBuilder().token(config.bot_token).post_init(_on_post_init).build()

    # Store shared services in bot_data
    app.bot_data["config"] = config
    app.bot_data["storage"] = storage
    app.bot_data["scraper"] = scraper

    # Single generic message handler catches all user texts & /start (NO commands)
    app.add_handler(MessageHandler(filters.ALL, generic_message_handler))

    # Single callback query router catches all inline buttons
    app.add_handler(CallbackQueryHandler(callback_router))

    # Error handler
    app.add_error_handler(global_error_handler)

    # Schedule background alert polling if job queue is available and alert_chat_id is configured
    if app.job_queue and config.alert_chat_id:
        interval_seconds = config.poll_minutes * 60
        logger.info(
            "Scheduling auto-alert job every %d seconds for chat_id=%d",
            interval_seconds,
            config.alert_chat_id,
        )
        app.job_queue.run_repeating(
            alert_poll_job,
            interval=interval_seconds,
            first=10,
        )

    return app


def main() -> None:
    """Bootstrap configuration and start long-polling."""
    config = Config.from_env()
    logger.info("Starting Telegram Orders Bot (Buttons Only mode)...")
    logger.info("Script Portal URL: %s", config.script_url)
    logger.info("Allowed User IDs: %s", config.allowed_user_ids or "Public Access (All)")

    app = create_application(config)
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
