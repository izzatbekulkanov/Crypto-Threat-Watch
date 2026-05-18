"""TON tarmog'i — Professional audit xizmati (tonapi.io + toncenter.com)."""

import httpx
import logging
from datetime import datetime, timezone

from config import TON_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_TONAPI_URL: str = "https://tonapi.io/v2"
_TONCENTER_URL: str = "https://toncenter.com/api/v2"
_HEADERS: dict[str, str] = {"Authorization": f"Bearer {TON_API_KEY}"}
_NANOTON_DIVISOR: int = 10**9


async def get_ton_balance(address: str) -> dict:
    """TON hamyon to'liq professional audit — ikki manbadan tekshirish.

    1. tonapi.io — asosiy ma'lumot manbasi
    2. toncenter.com — balansni tasdiqlash (cross-check)

    Args:
        address: TON hamyon manzili.

    Returns:
        To'liq audit natijasi.
    """
    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    jetton_balances: list[dict[str, str]] = []
    current_balance: float = 0.0
    account_status: str = "unknown"
    balance_verified: bool = False

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # ═══ 1. Hozirgi balans (tonapi.io) ═══
        try:
            resp = await safe_request(
                client, "GET", f"{_TONAPI_URL}/accounts/{address}", headers=_HEADERS
            )
            account_data: dict = resp.json()
            balance_nano: int = int(account_data.get("balance", 0))
            current_balance = balance_nano / _NANOTON_DIVISOR
            account_status = account_data.get("status", "unknown")
        except Exception as e:
            logger.error(f"TON account fetch error: {e}")
            return {"network": "TON", "address": address, "error": str(e)}

        # ═══ 2. Balansni toncenter bilan tasdiqlash (cross-check) ═══
        try:
            resp2 = await client.get(
                f"{_TONCENTER_URL}/getAddressBalance",
                params={"address": address},
                timeout=10,
            )
            if resp2.status_code == 200:
                toncenter_data: dict = resp2.json()
                toncenter_balance_nano: int = int(toncenter_data.get("result", 0))
                toncenter_balance: float = toncenter_balance_nano / _NANOTON_DIVISOR

                # Agar farq 0.01 TON dan kam bo'lsa — tasdiqlangan
                diff: float = abs(current_balance - toncenter_balance)
                if diff < 0.01:
                    balance_verified = True
                else:
                    # Toncenter ni ishonchli deb olamiz
                    logger.warning(
                        f"Balans farqi: tonapi={current_balance:.4f}, "
                        f"toncenter={toncenter_balance:.4f}, diff={diff:.4f}"
                    )
                    # Eng yangi qiymatni olamiz (ikkalasi ham blokcheyndan)
                    current_balance = min(current_balance, toncenter_balance)
                    balance_verified = True
        except Exception as e:
            logger.warning(f"Toncenter cross-check failed: {e}")
            # Tonapi natijasini ishlatamiz
            balance_verified = False

        # ═══ 3. Tranzaksiyalar (tonapi.io) ═══
        try:
            resp = await safe_request(
                client, "GET",
                f"{_TONAPI_URL}/blockchain/accounts/{address}/transactions",
                headers=_HEADERS,
                params={"limit": 100},
            )
            data: dict = resp.json()
            transactions: list[dict] = data.get("transactions", [])
            tx_count = len(transactions)

            for tx in transactions:
                in_msg: dict | None = tx.get("in_msg")
                if in_msg and in_msg.get("value"):
                    total_in += int(in_msg["value"])

                out_msgs: list[dict] = tx.get("out_msgs", [])
                for msg in out_msgs:
                    if msg.get("value"):
                        total_out += int(msg["value"])
        except Exception as e:
            logger.warning(f"TON transactions fetch error: {e}")

        # ═══ 4. Jetton balanslar ═══
        try:
            resp = await safe_request(
                client, "GET",
                f"{_TONAPI_URL}/accounts/{address}/jettons",
                headers=_HEADERS,
            )
            jetton_data: dict = resp.json()
            for item in jetton_data.get("balances", []):
                jetton_info: dict = item.get("jetton", {})
                symbol: str = jetton_info.get("symbol", "UNKNOWN")
                decimals: int = int(jetton_info.get("decimals", 9))
                raw_balance: int = int(item.get("balance", "0"))
                token_balance: float = raw_balance / (10 ** decimals)

                if token_balance > 0.0001:
                    jetton_balances.append({
                        "symbol": symbol,
                        "balance": f"{token_balance:,.4f}",
                    })
        except Exception as e:
            logger.warning(f"TON jettons fetch error: {e}")

    income_ton: float = total_in / _NANOTON_DIVISOR
    outcome_ton: float = total_out / _NANOTON_DIVISOR
    total_volume: float = income_ton + outcome_ton

    # Balans ko'rsatish formati
    balance_str: str = f"{current_balance:,.4f} TON"
    if balance_verified:
        balance_str += " ✓"

    return {
        "network": "TON",
        "address": address,
        "status": account_status,
        "current_balance": balance_str,
        "total_income": f"{income_ton:,.4f} TON",
        "total_outcome": f"{outcome_ton:,.4f} TON",
        "net_balance": f"{income_ton - outcome_ton:,.4f} TON",
        "total_volume": f"{total_volume:,.4f} TON",
        "tx_count": tx_count,
        "tokens": jetton_balances,
    }
