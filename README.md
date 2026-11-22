# Telegram Orders & Returns Bot

A button-driven, production-ready Telegram bot built with Python 3.11+ and `python-telegram-bot` (v21+). It reads live order tracking, return submissions, and payment settlement records from a public Google Apps Script web application.

---

## Architecture & Inspection Findings

### Step 1: Inspection of the Apps Script Web App
* **URL:** `https://script.google.com/macros/s/AKfycbzqOmNRuLVKPAXtS3xwoSRxCzdRp-kOAyeseP9zmNolgp9IPeYyR1cK9hAS0t-2w7XX/exec`
* **Response Type:** HTML wrapper with client-side JavaScript iframe (`/userCodeAppPanel`).
* **Mechanism:** The front-end renders a single-order tracking form (`#orderId` input and `#btnCheck` button). When queried, client JS calls `google.script.run.checkStatus(orderId)` via Google's underlying RPC callback endpoint:
  ```http
  POST https://script.google.com/macros/s/AKfycbzqOmNRuLVKPAXtS3xwoSRxCzdRp-kOAyeseP9zmNolgp9IPeYyR1cK9hAS0t-2w7XX/callback
  ```
  with form payload:
  ```text
  request=["checkStatus","[\"<order_id>\"]",null,[0],null,null,1,0]
  ```
* **Payload Response:**
  Google prefixes the RPC response with `)]}'\n` followed by an array containing `["op.exec", [0, "{\"amount\":58,\"buyerName\":\"Raina tapadar\",\"step2\":\"Refund Form Filled\",\"orderDate\":\"10-11-2026\",\"step3\":\"WILL BE DONE SOON\",\"step1\":\"Order Placed\"}"]]`.

### Field Mapping

| Portal Field | Bot Model Property | Type | Description | Sample Value |
|---|---|---|---|---|
| Input Parameter | `order_id` | String | 18-digit unique order identifier | `351692994041939520` |
| `buyerName` | `buyer_name` | String | Customer full name (Sold to) | `Raina tapadar` |
| `amount` | `amount` | Float | Order amount in INR (₹) | `58.00` |
| `orderDate` | `order_date` | String | Order creation date (DD-MM-YYYY) | `10-11-2026` |
| `step1` | `order_status` | String | Milestone 1: Confirmation | `Order Placed` |
| `step2` | `return_status` | String | Milestone 2: Refund form status | `Refund Form Filled` / `Pending` |
| `step3` | `settlement_status` | String | Milestone 3: Payment settlement | `WILL BE DONE SOON` / `Pending` |
| Derived | `is_return` | Boolean | True if refund form is filled or in settlement | `True` / `False` |

---

## BotFather Setup (No Commands Mode)

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**.
2. Send `/newbot` and provide a name and username ending in `bot`.
3. Copy the HTTP API token into your `.env` file as `TELEGRAM_BOT_TOKEN`.
4. **Important:** Do NOT run `/setcommands`. Leave the command menu empty so users interact entirely through buttons.

---

## Configuration (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | Bot token from @BotFather |
| `SCRIPT_URL` | No | Target Apps Script URL | Portal web app URL |
| `ALLOWED_USER_IDS` | No | *(empty = public)* | Comma-separated list of allowed Telegram user IDs |
| `POLL_MINUTES` | No | `5` | Background check interval for new orders/returns |
| `ALERT_CHAT_ID` | No | *(none)* | Telegram Chat ID to receive automated alerts |
| `DATABASE_PATH` | No | `orders.db` | Path to persistent SQLite database |
| `CACHE_TTL_SECONDS` | No | `60` | In-memory cache validity period |

---

## Local Run Guide

### 1. Set up Python Environment
```bash
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Run Tests & Linter
```bash
pytest -v
ruff check .
```

### 3. Launch Bot
```bash
python -m bot.main
```

---

## Docker Run Guide

### 1. Build and Run Container
```bash
docker build -t telegram-orders-bot .
docker run -d \
  --name orders-bot \
  --restart unless-stopped \
  -v $(pwd)/data:/app/data \
  -e TELEGRAM_BOT_TOKEN="your_token_here" \
  telegram-orders-bot
```

---

## Cloud Deployment Options

### 1-Click Deploy to Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/forbesayush/telegram-orders-bot)

1. Click the button above (or open [Render Blueprint](https://render.com/deploy?repo=https://github.com/forbesayush/telegram-orders-bot)).
2. Sign in with GitHub.
3. Fill in your `TELEGRAM_BOT_TOKEN`.
4. Click **Apply** — Render will build and deploy the bot with automated health checks on port `$PORT`.

On Render, Telegram sends messages to /telegram over HTTPS. A message can wake an idle free instance. Point uptime monitors at /healthz (GET or HEAD). The first reply after idle can take about a minute. Scheduled alerts only run while the process is awake. For continuous alerts, use an always-on instance and run one bot replica.

### Railway / Fly.io
1. Connect this GitHub repository.
2. Set the environment variable `TELEGRAM_BOT_TOKEN` in the service dashboard.
3. Choose the Dockerfile runtime or Python 3.11 environment (`python -m bot.main`).

### VPS with systemd
Create `/etc/systemd/system/orders-bot.service`:
```ini
[Unit]
Description=Telegram Orders Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/telegram-orders-bot
EnvironmentFile=/opt/telegram-orders-bot/.env
ExecStart=/opt/telegram-orders-bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
systemctl daemon-reload
systemctl enable --now orders-bot
```
