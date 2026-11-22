"""Configuration management for the Telegram Orders Bot.

Loads configuration from environment variables and an optional .env file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root if present
_ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT_DIR / ".env")

DEFAULT_SCRIPT_URL = (
    "https://script.google.com/macros/s/AKfycbzqOmNRuLVKPAXtS3xwoSRxCzdRp-kOAyeseP9zmNolgp9IPeYyR1cK9hAS0t-2w7XX/exec"
)

# Known order IDs from the master tracking portal
DEFAULT_SEED_ORDER_IDS = [
    "351692994041939520",
    "351693838664795200",
    "351689366156167936",
    "352437536531492992",
    "351686981576903424",
    "352439260149515136",
    "352434540123063872",
    "352436829206414208",
    "352436181348469504",
    "351684843438801984",
    "351688334581284992",
    "352046418968356800",
    "351691499350459456",
    "352042658904867904",
    "351696704611723200",
    "351696048292169280",
    "351694928855249024",
]


@dataclass(frozen=True)
class Config:
    """Application configuration container."""

    bot_token: str
    script_url: str = DEFAULT_SCRIPT_URL
    allowed_user_ids: set[int] = field(default_factory=set)
    poll_minutes: int = 5
    alert_chat_id: int | None = None
    seed_order_ids: list[str] = field(default_factory=lambda: list(DEFAULT_SEED_ORDER_IDS))
    database_path: str = "orders.db"
    cache_ttl_seconds: int = 60
    http_timeout: float = 35.0

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "TELEGRAM_BOT_TOKEN environment variable is missing or empty. "
                "Please set it in your .env file or environment."
            )

        script_url = os.getenv("SCRIPT_URL", DEFAULT_SCRIPT_URL).strip() or DEFAULT_SCRIPT_URL

        # Parse allowed user IDs (comma-separated list of integers)
        allowed_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
        allowed_ids: set[int] = set()
        if allowed_raw:
            for item in allowed_raw.split(","):
                clean = item.strip()
                if clean:
                    try:
                        allowed_ids.add(int(clean))
                    except ValueError:
                        pass

        # Parse alert chat ID
        alert_chat_raw = os.getenv("ALERT_CHAT_ID", "").strip()
        alert_chat_id: int | None = None
        if alert_chat_raw:
            try:
                alert_chat_id = int(alert_chat_raw)
            except ValueError:
                pass

        # Parse seed order IDs if provided via env
        seed_raw = os.getenv("SEED_ORDER_IDS", "").strip()
        if seed_raw:
            seed_ids = [s.strip() for s in seed_raw.split(",") if s.strip()]
        else:
            seed_ids = list(DEFAULT_SEED_ORDER_IDS)

        poll_minutes_raw = os.getenv("POLL_MINUTES", "5").strip()
        try:
            poll_minutes = max(1, int(poll_minutes_raw))
        except ValueError:
            poll_minutes = 5

        db_path = os.getenv("DATABASE_PATH", "orders.db").strip() or "orders.db"

        return cls(
            bot_token=token,
            script_url=script_url,
            allowed_user_ids=allowed_ids,
            poll_minutes=poll_minutes,
            alert_chat_id=alert_chat_id,
            seed_order_ids=seed_ids,
            database_path=db_path,
        )
