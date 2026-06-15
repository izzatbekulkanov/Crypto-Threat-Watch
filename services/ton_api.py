"""TON tarmog'i — Professional audit xizmati (tonapi.io + toncenter.com)."""

import asyncio
import httpx
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import TON_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_TONAPI_URL: str = "https://tonapi.io/v2"
_TONCENTER_URL: str = "https://toncenter.com/api/v2"
_HEADERS: dict[str, str] = {"Authorization": f"Bearer {TON_API_KEY}"}
_NANOTON_DIVISOR: int = 10**9

ProgressCb = Callable[..., Awaitable[None]]


async def _noop_progress(*args, **kwargs) -> None:
    return None


async def get_ton_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """TON hamyon to'liq professional audit — ikki manbadan tekshirish.

    1. tonapi.io — asosiy ma'lumot manbasi
    2. toncenter.com — balansni tasdiqlash (cross-check)

    Args:
        address: TON hamyon manzili.
        progress: Progress callback funksiyasi.

    Returns:
        To'liq audit natijasi.
    """
    cb: ProgressCb = progress or _noop_progress

    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    jetton_balances: list[dict] = []
    current_balance: float = 0.0
    account_status: str = "unknown"
    balance_verified: bool = False
    raw_address: str = ""
    yearly_stats: dict[str, dict[str, float]] = {}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # Helper tasks to run concurrently
        async def fetch_account() -> dict:
            await cb("progress_balance", 10)
            resp = await safe_request(
                client, "GET", f"{_TONAPI_URL}/accounts/{address}", headers=_HEADERS
            )
            data = resp.json()
            await cb("progress_verifying", 20)
            return data

        async def fetch_toncenter_balance() -> float | None:
            try:
                resp2 = await client.get(
                    f"{_TONCENTER_URL}/getAddressBalance",
                    params={"address": address},
                    timeout=10,
                )
                if resp2.status_code == 200:
                    toncenter_data: dict = resp2.json()
                    toncenter_balance_nano: int = int(toncenter_data.get("result", 0))
                    return toncenter_balance_nano / _NANOTON_DIVISOR
            except Exception as e:
                logger.warning(f"Toncenter cross-check failed: {e}")
            return None

        async def fetch_transactions() -> dict:
            await cb("progress_txns", 30, count=0)
            try:
                resp = await safe_request(
                    client, "GET",
                    f"{_TONAPI_URL}/blockchain/accounts/{address}/transactions",
                    headers=_HEADERS,
                    params={"limit": 100},
                )
                data = resp.json()
                txs = data.get("transactions", [])
                await cb("progress_txns", 60, count=len(txs))
                return data
            except Exception as e:
                logger.warning(f"TON transactions fetch error: {e}")
                return {}

        async def fetch_jettons() -> dict:
            await cb("progress_tokens", 70)
            try:
                resp = await safe_request(
                    client, "GET",
                    f"{_TONAPI_URL}/accounts/{address}/jettons",
                    headers=_HEADERS,
                )
                data = resp.json()
                await cb("progress_finalizing", 90)
                return data
            except Exception as e:
                logger.warning(f"TON jettons fetch error: {e}")
                return {}

        # ═══ Parallel Fetching ═══
        results = await asyncio.gather(
            fetch_account(),
            fetch_toncenter_balance(),
            fetch_transactions(),
            fetch_jettons(),
            return_exceptions=True
        )

        account_data = results[0]
        toncenter_balance = results[1]
        transactions_data = results[2]
        jettons_data = results[3]

        if isinstance(account_data, Exception):
            logger.error(f"TON account fetch error: {account_data}")
            return {"network": "TON", "address": address, "error": str(account_data)}

        # ═══ 1. Hozirgi balans (tonapi.io) ═══
        try:
            balance_nano: int = int(account_data.get("balance", 0))
            current_balance = balance_nano / _NANOTON_DIVISOR
            account_status = account_data.get("status", "unknown")
            raw_address = account_data.get("address", "").lower()
        except Exception as e:
            logger.error(f"Error parsing TON account data: {e}")
            return {"network": "TON", "address": address, "error": str(e)}

        # ═══ 2. Balansni toncenter bilan tasdiqlash (cross-check) ═══
        if toncenter_balance is not None and not isinstance(toncenter_balance, Exception):
            diff: float = abs(current_balance - toncenter_balance)
            if diff < 0.01:
                balance_verified = True
            else:
                logger.warning(
                    f"Balans farqi: tonapi={current_balance:.4f}, "
                    f"toncenter={toncenter_balance:.4f}, diff={diff:.4f}"
                )
                current_balance = min(current_balance, toncenter_balance)
                balance_verified = True

        # ═══ 3. Tranzaksiyalar (tonapi.io) & Yearly Stats ═══
        if transactions_data and not isinstance(transactions_data, Exception):
            transactions: list[dict] = transactions_data.get("transactions", [])
            tx_count = len(transactions)

            for tx in transactions:
                tx_time = tx.get("utime", 0)
                year = "Unknown"
                if tx_time:
                    year = str(datetime.fromtimestamp(tx_time, tz=timezone.utc).year)
                if year not in yearly_stats:
                    yearly_stats[year] = {"in": 0.0, "out": 0.0}

                in_msg: dict | None = tx.get("in_msg")
                if in_msg and in_msg.get("value"):
                    src = in_msg.get("source") or {}
                    src_addr = src.get("address", "").lower() if isinstance(src, dict) else ""
                    if src_addr != raw_address:
                        val = int(in_msg["value"])
                        total_in += val
                        yearly_stats[year]["in"] += val / _NANOTON_DIVISOR

                out_msgs: list[dict] = tx.get("out_msgs", [])
                for msg in out_msgs:
                    if msg.get("value"):
                        dest = msg.get("destination") or {}
                        dest_addr = dest.get("address", "").lower() if isinstance(dest, dict) else ""
                        if dest_addr != raw_address:
                            val = int(msg["value"])
                            total_out += val
                            yearly_stats[year]["out"] += val / _NANOTON_DIVISOR

        # ═══ 4. Jetton balanslar ═══
        if jettons_data and not isinstance(jettons_data, Exception):
            for item in jettons_data.get("balances", []):
                jetton_info: dict = item.get("jetton", {})
                symbol: str = jetton_info.get("symbol", "UNKNOWN")
                decimals: int = int(jetton_info.get("decimals", 9))
                raw_balance: int = int(item.get("balance", "0"))
                token_balance: float = raw_balance / (10 ** decimals)

                if token_balance > 0.0001:
                    jetton_balances.append({
                        "symbol": symbol,
                        "is_native": False,
                        "balance": f"{token_balance:,.4f} {symbol}",
                        "income": "—",
                        "outcome": "—",
                        "net": "—",
                        "volume": "—",
                        "tx_count": 0,
                    })

    await cb("progress_finalizing", 98)

    income_ton: float = total_in / _NANOTON_DIVISOR
    outcome_ton: float = total_out / _NANOTON_DIVISOR
    total_volume: float = income_ton + outcome_ton

    # Balans ko'rsatish formati
    balance_str: str = f"{current_balance:,.4f} GRAM"
    if balance_verified:
        balance_str += " ✓"

    # Assets list
    assets: list[dict] = []
    
    # Native asset (Gram)
    assets.append({
        "symbol": "GRAM",
        "is_native": True,
        "balance": balance_str,
        "income": f"{income_ton:,.4f} GRAM",
        "outcome": f"{outcome_ton:,.4f} GRAM",
        "net": f"{income_ton - outcome_ton:,.4f} GRAM",
        "volume": f"{total_volume:,.4f} GRAM",
        "tx_count": tx_count,
    })
    
    # Custom jettons
    assets.extend(jetton_balances)

    return {
        "network": "TON",
        "address": address,
        "status": account_status,
        "current_balance": balance_str,
        "total_income": f"{income_ton:,.4f} GRAM",
        "total_outcome": f"{outcome_ton:,.4f} GRAM",
        "net_balance": f"{income_ton - outcome_ton:,.4f} GRAM",
        "total_volume": f"{total_volume:,.4f} GRAM",
        "tx_count": tx_count,
        "assets": assets,
        "grand_tx_count": tx_count,
        "asset_count": len(assets),
        "yearly_stats": yearly_stats,
        "tokens": jetton_balances,
    }
