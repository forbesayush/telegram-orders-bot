"""Unit tests for Scraper and Google Apps Script parser."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

from bs4 import BeautifulSoup

from bot.scraper import Order, Scraper


def test_parse_html_tables():
    """Verify HTML table parsing extracts order fields."""
    html = """
    <table>
        <tr><th>Order ID</th><th>Buyer</th><th>Amount</th><th>Date</th><th>Status</th><th>Return</th></tr>
        <tr><td>351692994041939520</td><td>Alice</td><td>₹58.00</td><td>10-11-2026</td><td>Order Placed</td><td>Refund Form Filled</td></tr>
        <tr><td>351693838664795200</td><td>Bob</td><td>₹60.00</td><td>10-11-2026</td><td>Order Placed</td><td>Pending</td></tr>
    </table>
    """
    soup = BeautifulSoup(html, "html.parser")
    scraper = Scraper("https://example.com/exec")
    orders = scraper._parse_html_tables(soup.find_all("table"))

    assert len(orders) == 2
    assert orders[0].order_id == "351692994041939520"
    assert orders[0].buyer_name == "Alice"
    assert orders[0].amount == 58.0
    assert orders[0].is_return is True

    assert orders[1].order_id == "351693838664795200"
    assert orders[1].buyer_name == "Bob"
    assert orders[1].is_return is False


def test_fetch_order_direct_rpc_parsing():
    """Verify parsing of Google Apps Script RPC prefix and JSON payload."""

    async def _run():
        rpc_payload = ")]}'\n" + json.dumps([
            [
                "op.exec",
                [
                    0,
                    json.dumps({
                        "amount": 58,
                        "buyerName": "Raina tapadar",
                        "step2": "Refund Form Filled",
                        "orderDate": "10-11-2026",
                        "step3": "WILL BE DONE SOON",
                        "step1": "Order Placed",
                    }),
                ],
            ],
            ["di", 14158],
        ])

        scraper = Scraper("https://script.google.com/macros/s/TEST/exec")

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = rpc_payload
            mock_post.return_value = mock_response

            order = await scraper.fetch_order_direct("351692994041939520")

            assert order is not None
            assert order.order_id == "351692994041939520"
            assert order.buyer_name == "Raina tapadar"
            assert order.amount == 58.0
            assert order.order_date == "10-11-2026"
            assert order.order_status == "Order Placed"
            assert order.return_status == "Refund Form Filled"
            assert order.settlement_status == "WILL BE DONE SOON"
            assert order.is_return is True

    asyncio.run(_run())


def test_fetch_order_direct_invalid_id():
    """Invalid order ID should return None."""

    async def _run():
        rpc_payload = ")]}'\n" + json.dumps([
            ["op.exec", [0, "Invalid Order ID"]],
        ])

        scraper = Scraper("https://script.google.com/macros/s/TEST/exec")

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = rpc_payload
            mock_post.return_value = mock_response

            order = await scraper.fetch_order_direct("999999999999999999")
            assert order is None

    asyncio.run(_run())


def test_caching_behavior():
    """Within cache TTL, subsequent calls should not make network requests."""

    async def _run():
        scraper = Scraper("https://script.google.com/macros/s/TEST/exec", cache_ttl=60)
        fake_order = Order(
            order_id="123",
            buyer_name="Test",
            amount=50.0,
            order_date="10-11-2026",
            order_status="Placed",
            return_status="Pending",
            settlement_status="Pending",
            is_return=False,
        )

        with patch.object(scraper, "fetch_order_direct", AsyncMock(return_value=fake_order)) as mock_fetch:
            res1 = await scraper.fetch_all_orders(["123"], force_refresh=False)
            assert len(res1) == 1
            assert mock_fetch.call_count == 1

            res2 = await scraper.fetch_all_orders(["123"], force_refresh=False)
            assert len(res2) == 1
            assert mock_fetch.call_count == 1

            res3 = await scraper.fetch_all_orders(["123"], force_refresh=True)
            assert len(res3) == 1
            assert mock_fetch.call_count == 2

    asyncio.run(_run())
