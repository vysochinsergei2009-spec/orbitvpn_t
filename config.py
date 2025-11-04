import json
import os
from pathlib import Path
from typing import Any, Final

from aiogram import Bot
from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(Exception):
    pass


def _get_required_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise ConfigurationError(f"Required environment variable '{key}' is not set")
    return value


def _get_env_int(key: str, default: int) -> int:
    value = os.getenv(key)
    return int(value) if value else default


def _get_env_float(key: str, default: float) -> float:
    value = os.getenv(key)
    return float(value) if value else default


def _load_plans(file_path: str = "plans.json") -> dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        raise ConfigurationError(f"Plans file not found: {file_path}")

    with path.open("r", encoding="utf-8") as f:
        plans = json.load(f)

    price_overrides = {
        "sub_1m": "SUB_1M_PRICE",
        "sub_3m": "SUB_3M_PRICE",
        "sub_6m": "SUB_6M_PRICE",
        "sub_12m": "SUB_12M_PRICE",
    }

    for plan_key, env_var in price_overrides.items():
        if plan_key in plans and (override := os.getenv(env_var)):
            plans[plan_key]["price"] = int(override)

    return plans


# --- Telegram Bot Configuration ---
BOT_TOKEN: Final[str] = _get_required_env("BOT_TOKEN")
ADMIN_TG_ID: Final[int] = _get_env_int("ADMIN_TG_ID", 0)  # Admin Telegram ID for admin panel access

bot: Final[Bot] = Bot(token=BOT_TOKEN)

# --- Installation Guide URLs ---
INSTALL_GUIDE_BASE_URL: Final[str] = "https://orbitcorp.space"
INSTALL_GUIDE_URLS: Final[dict[str, str]] = {
    "ru": f"{INSTALL_GUIDE_BASE_URL}/install/ru",
    "en": f"{INSTALL_GUIDE_BASE_URL}/install/en",
}
PRIVACY_POLICY_URLS: Final[dict[str, str]] = {
    "ru": f"{INSTALL_GUIDE_BASE_URL}/policy/ru",
    "en": f"{INSTALL_GUIDE_BASE_URL}/policy/en",
}

# --- Logging Configuration ---
IS_LOGGING: Final[bool] = True
LOG_LEVEL: Final[str] = "INFO"  # Options: "INFO", "DEBUG", "ERROR"
LOG_AIOGRAM: Final[bool] = False

# --- Database Configuration ---
DATABASE_USER: Final[str] = _get_required_env("DATABASE_USER")
DATABASE_PASSWORD: Final[str] = _get_required_env("DATABASE_PASSWORD")
DATABASE_NAME: Final[str] = _get_required_env("DATABASE_NAME")
DATABASE_HOST: Final[str] = _get_required_env("DATABASE_HOST")

# --- Redis Configuration ---
REDIS_URL: Final[str] = os.getenv("REDIS_URL", "redis://localhost")
REDIS_TTL: Final[int] = 300  # Cache TTL in seconds (5 minutes)

# --- Server Configuration ---
PORT: Final[int] = _get_env_int("PORT", 5000)

# --- Marzban VPN Panel Configuration ---
# DEPRECATED: These single-instance configs are kept for backward compatibility
# New deployments should use marzban_instances table in database
S001_MARZBAN_USERNAME: Final[str] = _get_required_env("S001_MARZBAN_USERNAME")
S001_MARZBAN_PASSWORD: Final[str] = _get_required_env("S001_MARZBAN_PASSWORD")
S001_BASE_URL: Final[str] = os.getenv("S001_BASE_URL", "https://s001.orbitcorp.space:8000/")

# Note: To add multiple Marzban instances, insert them into marzban_instances table:
# INSERT INTO marzban_instances (id, name, base_url, username, password, is_active, priority)
# VALUES ('s001', 'Main Server', 'https://...', 'username', 'password', TRUE, 100);

# --- TON Payment Gateway Configuration ---
TON_ADDRESS: Final[str] = _get_required_env("TON_ADDRESS")
TONAPI_URL: Final[str] = _get_required_env("TONAPI_URL")
TONAPI_KEY: Final[str] = _get_required_env("TONAPI_KEY")
TON_EXPLORER_TX_URL: Final[str] = f"https://tonviewer.com/{TON_ADDRESS}"
TON_CHECK_INTERVAL: Final[int] = 30  # Blockchain polling interval in seconds

# --- CryptoBot Payment Gateway Configuration ---
CRYPTOBOT_TOKEN: Final[str] = os.getenv("CRYPTOBOT_TOKEN", "")  # Optional: will be set in .env
CRYPTOBOT_TESTNET: Final[bool] = os.getenv("CRYPTOBOT_TESTNET", "false").lower() == "true"

# --- YooKassa Payment Gateway Configuration ---
# Production credentials
YOOKASSA_SHOP_ID: Final[str] = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY: Final[str] = os.getenv("YOOKASSA_SECRET_KEY", "")

# Test credentials (separate test shop)
YOOKASSA_TEST_SHOP_ID: Final[str] = os.getenv("YOOKASSA_TEST_SHOP_ID", "")
YOOKASSA_TEST_SECRET_KEY: Final[str] = os.getenv("YOOKASSA_TEST_SECRET_KEY", "")

# Mode selector
YOOKASSA_TESTNET: Final[bool] = os.getenv("YOOKASSA_TESTNET", "false").lower() == "true"

# --- Payment Configuration ---
PAYMENT_TIMEOUT_MINUTES: Final[int] = 15  # Auto-expire pending payments after 15 minutes
TELEGRAM_STARS_RATE: Final[float] = 1.35  # Stars to RUB conversion

# --- Business Logic Constants ---
FREE_TRIAL_DAYS: Final[int] = 7
REFERRAL_BONUS: Final[float] = 50.0
MAX_IPS_PER_CONFIG: Final[int] = _get_env_int("MAX_IPS_PER_CONFIG", 2)  # Max concurrent devices per VPN config

# --- Subscription Plans ---
PLANS: Final[dict[str, Any]] = _load_plans()
