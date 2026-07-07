"""Loyiha konfiguratsiyasi — atrof-muhit o'zgaruvchilarini xavfsiz yuklash."""

import os
from pathlib import Path

from dotenv import load_dotenv

# .env faylini yuklash
env_path: Path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


def _get_env(key: str) -> str:
    """Majburiy muhit o'zgaruvchisini olish. Bo'sh bo'lsa xatolik."""
    value: str | None = os.getenv(key)
    if not value:
        raise ValueError(f"'{key}' muhit o'zgaruvchisi topilmadi. .env faylini tekshiring.")
    return value


def _get_env_optional(key: str, default: str = "") -> str:
    """Ixtiyoriy muhit o'zgaruvchisini olish."""
    return os.getenv(key, default) or default


# Telegram
BOT_TOKEN: str = _get_env("BOT_TOKEN")

# Blokcheyn API kalitlari
TON_API_KEY: str = _get_env("TON_API_KEY")
ETHERSCAN_API_KEY: str = _get_env("ETHERSCAN_API_KEY")
TRONGRID_API_KEY: str = _get_env("TRONGRID_API_KEY")

# L2 API kalitlari (ixtiyoriy)
BSCSCAN_API_KEY: str = _get_env_optional("BSCSCAN_API_KEY", "")
POLYGONSCAN_API_KEY: str = _get_env_optional("POLYGONSCAN_API_KEY", "")
BASESCAN_API_KEY: str = _get_env_optional("BASESCAN_API_KEY", "")

# Admin paroli
ADMIN_PASSWORD: str = _get_env_optional("ADMIN_PASSWORD", "kronos")

# Rate limiting
RATE_LIMIT_PER_MINUTE: int = int(_get_env_optional("RATE_LIMIT_PER_MINUTE", "10"))

# GitHub Pages Web App URL (/web uchun kerak)
WEBAPP_URL: str = _get_env_optional("WEBAPP_URL", "")
