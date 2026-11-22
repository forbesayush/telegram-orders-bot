from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.main import build_web_service


@pytest.mark.asyncio
async def test_webhook_and_monitor():
    app = AsyncMock()
    app.running = True
    app.updater.running = False
    app.bot.token = "test-token"
    app.bot.defaults = None
    async with TestClient(TestServer(build_web_service(app, "https://bot.example/"))) as client:
        registration = app.bot.set_webhook.await_args.kwargs
        assert registration["url"] == "https://bot.example/telegram"
        assert registration["drop_pending_updates"] is False
        for path in ("/", "/healthz"):
            assert (await client.head(path)).status == 200
        assert (await client.post("/telegram", json={"update_id": 1})).status == 403
        headers = {"X-Telegram-Bot-Api-Secret-Token": registration["secret_token"]}
        assert (await client.post("/telegram", headers=headers, json={"update_id": 1})).status == 200
        assert app.update_queue.put.await_args.args[0].update_id == 1
    app.stop.assert_awaited_once()
    app.bot.delete_webhook.assert_not_awaited()


@pytest.mark.asyncio
async def test_port_only_preserves_polling():
    app = AsyncMock()
    app.bot.token = "test-token"
    app.updater = SimpleNamespace(start_polling=AsyncMock(), stop=AsyncMock(), running=True)
    async with TestClient(TestServer(build_web_service(app, ""))) as client:
        app.updater.start_polling.assert_awaited_once_with(drop_pending_updates=False)
        assert (await client.post("/telegram")).status == 404
    app.updater.stop.assert_awaited_once()
