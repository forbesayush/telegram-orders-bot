"""Scraper and API client for the Google Apps Script Order Status Portal.

Handles initial URL inspection, direct Apps Script RPC calls, exponential
backoff, error handling, and in-memory TTL caching.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Order:
    """Normalized Order data model."""

    order_id: str
    buyer_name: str
    amount: float
    order_date: str
    order_status: str
    return_status: str
    settlement_status: str
    is_return: bool

    def to_dict(self) -> dict[str, Any]:
        """Convert Order instance to dictionary."""
        return asdict(self)


class Scraper:
    """Production client for inspecting and fetching orders from Google Apps Script."""

    def __init__(
        self,
        script_url: str,
        seed_order_ids: list[str] | None = None,
        cache_ttl: int = 60,
        timeout: float = 15.0,
    ) -> None:
        self.script_url = script_url
        self.seed_order_ids = list(seed_order_ids or [])
        self.cache_ttl = cache_ttl
        self.timeout = timeout

        self._cached_orders: list[Order] = []
        self._last_fetch_time: float = 0.0
        self._lock = asyncio.Lock()

        # Derive callback URL prefix
        parsed = urlparse(script_url)
        base_path = re.sub(r"/exec/?$", "", parsed.path)
        self.callback_url = f"{parsed.scheme}://{parsed.netloc}{base_path}/callback"
        self.exec_url = f"{parsed.scheme}://{parsed.netloc}{base_path}/exec"

    async def inspect_url(self) -> dict[str, Any]:
        """Probe the configured SCRIPT_URL to detect its format (JSON vs HTML vs JS App).

        Returns:
            Dictionary with inspection metadata: status, content_type,
            is_json, is_interactive_apps_script, parsed_count, sample.
        """
        logger.info("Inspecting target URL: %s", self.script_url)
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(self.script_url, headers=headers)
            content_type = resp.headers.get("content-type", "").lower()
            text = resp.text

            # Check for pure JSON output
            if "application/json" in content_type:
                try:
                    data = resp.json()
                    return {
                        "format": "JSON",
                        "status_code": resp.status_code,
                        "data": data,
                        "sample": data[:3] if isinstance(data, list) else data,
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning("JSON Content-Type header present but parsing failed: %s", e)

            # Check for HTML content
            soup = BeautifulSoup(text, "html.parser")
            tables = soup.find_all("table")
            table_orders = self._parse_html_tables(tables)

            if table_orders:
                return {
                    "format": "HTML_TABLE",
                    "status_code": resp.status_code,
                    "orders_count": len(table_orders),
                    "sample": table_orders[:2],
                }

            # Check if this is an interactive Google Apps Script UI
            is_apps_script_ui = (
                "goog.script.init" in text
                or "sandboxFrame" in text
                or "Order Status" in text
                or "userCodeAppPanel" in text
            )

            return {
                "format": "APPS_SCRIPT_CLIENT_UI" if is_apps_script_ui else "UNKNOWN_HTML",
                "status_code": resp.status_code,
                "is_interactive": is_apps_script_ui,
                "page_title": soup.title.string.strip() if soup.title and soup.title.string else None,
                "note": (
                    "Page renders an interactive single-order lookup UI (JavaScript sandboxed). "
                    "Underlying RPC endpoint is queried directly for order records."
                ),
            }

    def _parse_html_tables(self, tables: list[Any]) -> list[Order]:
        """Parse orders if rendered in static HTML tables."""
        orders: list[Order] = []
        for table in tables:
            rows = table.find_all("tr")
            for row in rows[1:]:  # skip potential header
                cols = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cols) >= 3 and re.match(r"^\d{15,20}$", cols[0]):
                    order_id = cols[0]
                    buyer = cols[1] if len(cols) > 1 else "N/A"
                    amount_match = re.search(r"[\d.]+", cols[2]) if len(cols) > 2 else None
                    amount = float(amount_match.group(0)) if amount_match else 0.0
                    date = cols[3] if len(cols) > 3 else "N/A"
                    status = cols[4] if len(cols) > 4 else "Confirmed"
                    return_st = cols[5] if len(cols) > 5 else "Pending"
                    is_return = "return" in return_st.lower() or "refund" in return_st.lower()
                    orders.append(
                        Order(
                            order_id=order_id,
                            buyer_name=buyer,
                            amount=amount,
                            order_date=date,
                            order_status=status,
                            return_status=return_st,
                            settlement_status="Pending",
                            is_return=is_return,
                        )
                    )
        return orders

    async def fetch_order_direct(self, order_id: str, retries: int = 3) -> Order | None:
        """Fetch a single order from the Google Apps Script RPC endpoint with exponential backoff."""
        url = self.callback_url
        request_arg = ["checkStatus", json.dumps([str(order_id)]), None, [0], None, None, 1, 0]
        body = f"request={httpx.URL('', params={'q': json.dumps(request_arg)}).query.decode('utf-8')[2:]}"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "X-Same-Domain": "1",
            "Referer": self.exec_url,
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

        delay = 1.0
        for attempt in range(retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                    resp = await client.post(url, headers=headers, content=body)

                if resp.status_code == 200:
                    text = resp.text.strip()
                    # Google Apps Script RPC response prefix: )]}'
                    if text.startswith(")]}'"):
                        text = text[4:].strip()

                    try:
                        parsed = json.loads(text)
                    except json.JSONDecodeError:
                        logger.warning("Failed to decode JSON from Apps Script RPC for %s", order_id)
                        return None

                    for item in parsed:
                        if isinstance(item, list) and len(item) > 1 and item[0] == "op.exec":
                            val = item[1][1] if isinstance(item[1], list) and len(item[1]) > 1 else None
                            if not val or val in ("Invalid Order ID", '"Invalid Order ID"'):
                                return None

                            if isinstance(val, str) and val.startswith('"') and val.endswith('"'):
                                try:
                                    val = json.loads(val)
                                except json.JSONDecodeError:
                                    pass

                            if val == "Invalid Order ID":
                                return None

                            data = json.loads(val) if isinstance(val, str) and val.startswith("{") else val
                            if isinstance(data, dict):
                                buyer_name = data.get("buyerName", "N/A")
                                amount = float(data.get("amount") or 0.0)
                                order_date = data.get("orderDate", "N/A")
                                order_status = data.get("step1", "Order Placed")
                                return_status = data.get("step2", "Pending")
                                settlement_status = data.get("step3", "Pending")

                                is_return = (
                                    return_status == "Refund Form Filled"
                                    or settlement_status in ("Refund Completed", "WILL BE DONE SOON")
                                )

                                return Order(
                                    order_id=str(order_id),
                                    buyer_name=buyer_name,
                                    amount=amount,
                                    order_date=order_date,
                                    order_status=order_status,
                                    return_status=return_status,
                                    settlement_status=settlement_status,
                                    is_return=is_return,
                                )

                    return None

                logger.warning(
                    "Apps Script returned status %d for %s (attempt %d/%d)",
                    resp.status_code,
                    order_id,
                    attempt + 1,
                    retries,
                )

            except (httpx.RequestError, httpx.TimeoutException) as exc:
                logger.warning(
                    "Network error fetching order %s (attempt %d/%d): %s",
                    order_id,
                    attempt + 1,
                    retries,
                    exc,
                )

            if attempt < retries - 1:
                await asyncio.sleep(delay)
                delay *= 2.0

        return None

    async def fetch_orders_batch(
        self, order_ids: list[str], concurrency: int = 5
    ) -> dict[str, Order | None]:
        """Fetch multiple orders from Google Apps Script concurrently."""
        sem = asyncio.Semaphore(concurrency)

        async def _fetch(oid: str) -> tuple[str, Order | None]:
            async with sem:
                res = await self.fetch_order_direct(oid)
                return oid, res

        tasks = [_fetch(oid) for oid in order_ids]
        results = await asyncio.gather(*tasks)
        return dict(results)

    async def fetch_all_orders(
        self,
        order_ids: list[str] | None = None,
        force_refresh: bool = False,
    ) -> list[Order]:
        """Fetch all orders with caching support.

        Args:
            order_ids: Optional list of order IDs to query. Defaults to seed_order_ids.
            force_refresh: If True, bypass the in-memory 60s TTL cache.
        """
        async with self._lock:
            now = time.time()
            if not force_refresh and self._cached_orders and (now - self._last_fetch_time < self.cache_ttl):
                logger.debug("Returning cached orders (age: %.1fs)", now - self._last_fetch_time)
                return self._cached_orders

            target_ids = list(order_ids or self.seed_order_ids)
            logger.info("Fetching orders for %d IDs (force_refresh=%s)...", len(target_ids), force_refresh)

            tasks = [self.fetch_order_direct(oid) for oid in target_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            orders: list[Order] = []
            for r in results:
                if isinstance(r, Order):
                    orders.append(r)
                elif isinstance(r, Exception):
                    logger.error("Error in batch fetch task: %s", r)

            self._cached_orders = orders
            self._last_fetch_time = time.time()
            return orders
