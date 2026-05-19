"""Yordamchi mantiqlar — havolalar va manzillarni tahlil qilish."""

import re
from typing import Optional


# ═══════════════════════════════════════════
# URL Regex shablonlari
# ═══════════════════════════════════════════
_TON_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?tonviewer\.com/([A-Za-z0-9_\-]{48})",
    re.IGNORECASE,
)

_TONSCAN_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?tonscan\.org/(?:[a-z]{2}/)?address/([A-Za-z0-9_\-]{48})",
    re.IGNORECASE,
)

_ETH_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?etherscan\.io/address/(0x[0-9a-fA-F]{40})",
    re.IGNORECASE,
)

_TRON_URL_PATTERN: re.Pattern[str] = re.compile(
    r"(?:https?://)?(?:www\.)?tronscan\.org/#/address/([A-Za-z0-9]{34})",
    re.IGNORECASE,
)

# ═══════════════════════════════════════════
# Raw manzil shablonlari (havola bo'lmasa)
# ═══════════════════════════════════════════

# Ethereum: 0x bilan boshlanadi, 40 ta hex belgi
_ETH_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"^(0x[0-9a-fA-F]{40})$"
)

# TRON: T bilan boshlanadi, 34 ta base58 belgi
_TRON_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"^(T[A-Za-z0-9]{33})$"
)

# TON: UQ yoki EQ bilan boshlanadi, 48 ta belgi (base64url)
# yoki 0: bilan boshlanadi (raw format)
_TON_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"^([UE]Q[A-Za-z0-9_\-]{46})$"
)

# TON raw format: 0:hex (66 belgi)
_TON_RAW_PATTERN: re.Pattern[str] = re.compile(
    r"^(0:[0-9a-fA-F]{64})$"
)


def parse_crypto_link(text: str) -> Optional[tuple[str, str]]:
    """Havolani YOKI to'g'ridan-to'g'ri manzilni tahlil qiladi.

    Avval URL formatini tekshiradi, keyin raw manzil formatini.

    Args:
        text: Foydalanuvchi yuborgan matn (havola yoki manzil).

    Returns:
        (tarmoq_nomi, hamyon_manzili) tuple yoki None.
    """
    text = text.strip()

    # ═══ 1. URL formatlarini tekshirish ═══

    # TONViewer URL
    match: Optional[re.Match[str]] = _TON_URL_PATTERN.search(text)
    if match:
        return ("TON", match.group(1))

    # TonScan URL
    match = _TONSCAN_URL_PATTERN.search(text)
    if match:
        return ("TON", match.group(1))

    # Etherscan URL
    match = _ETH_URL_PATTERN.search(text)
    if match:
        return ("ETH", match.group(1))

    # Tronscan URL
    match = _TRON_URL_PATTERN.search(text)
    if match:
        return ("TRON", match.group(1))

    # ═══ 2. Raw manzil formatlarini tekshirish ═══

    # Ethereum manzili (0x...)
    match = _ETH_ADDRESS_PATTERN.match(text)
    if match:
        return ("ETH", match.group(1))

    # TRON manzili (T...)
    match = _TRON_ADDRESS_PATTERN.match(text)
    if match:
        return ("TRON", match.group(1))

    # TON manzili (UQ... yoki EQ...)
    match = _TON_ADDRESS_PATTERN.match(text)
    if match:
        return ("TON", match.group(1))

    # TON raw format (0:hex)
    match = _TON_RAW_PATTERN.match(text)
    if match:
        return ("TON", match.group(1))

    return None
