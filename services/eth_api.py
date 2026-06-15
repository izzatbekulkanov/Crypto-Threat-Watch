"""Ethereum tarmog'i — Professional audit xizmati (etherscan.io)."""

import asyncio
import httpx
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import ETHERSCAN_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.etherscan.io/api"
_WEI_DIVISOR: int = 10**18

ProgressCb = Callable[..., Awaitable[None]]


async def _noop_progress(*args, **kwargs) -> None:
    return None


async def get_eth_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """Ethereum hamyon to'liq professional audit.

    - Hozirgi ETH balansi (real-time)
    - ETH kirim/chiqim/sof qoldiq
    - Jami tranzaksiyalar hajmi
    - ERC-20 tokenlar bo'yicha guruhlash (har bir token alohida)
    - Tranzaksiyalar soni

    Args:
        address: Ethereum hamyon manzili (0x...).
        progress: Progress callback funksiyasi.

    Returns:
        To'liq audit natijasi.
    """
    cb: ProgressCb = progress or _noop_progress

    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    current_balance: float = 0.0
    yearly_stats: dict[str, dict[str, float]] = {}

    # ERC-20 tokenlar
    token_data_map: dict[str, dict[str, float]] = {}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # Helper tasks
        async def fetch_balance() -> dict:
            await cb("progress_balance", 10)
            resp = await safe_request(
                client, "GET", _BASE_URL,
                params={
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest",
                    "apikey": ETHERSCAN_API_KEY,
                },
            )
            return resp.json()

        async def fetch_txlist() -> tuple[int, int, int, dict]:
            nonlocal total_in, total_out, tx_count
            await cb("progress_txns", 30, count=0)
            try:
                address_lower = address.lower()
                page = 1
                for _ in range(10): # Max 10 sahifa (100,000 tranzaksiya)
                    resp = await safe_request(
                        client, "GET", _BASE_URL,
                        params={
                            "module": "account",
                            "action": "txlist",
                            "address": address,
                            "startblock": "0",
                            "endblock": "99999999",
                            "sort": "desc",
                            "offset": "10000",
                            "page": str(page),
                            "apikey": ETHERSCAN_API_KEY,
                        },
                    )
                    data = resp.json()
                    transactions = data.get("result", [])

                    if not isinstance(transactions, list) or not transactions:
                        break

                    tx_count += len(transactions)

                    for tx in transactions:
                        value = int(tx.get("value", "0"))
                        if value == 0:
                            continue

                        tx_time = int(tx.get("timeStamp", "0"))
                        year = "Unknown"
                        if tx_time:
                            year = str(datetime.fromtimestamp(tx_time, tz=timezone.utc).year)
                        if year not in yearly_stats:
                            yearly_stats[year] = {"in": 0.0, "out": 0.0}

                        if tx.get("to", "").lower() == address_lower:
                            total_in += value
                            yearly_stats[year]["in"] += value / _WEI_DIVISOR
                        if tx.get("from", "").lower() == address_lower:
                            total_out += value
                            yearly_stats[year]["out"] += value / _WEI_DIVISOR
                    
                    if len(transactions) < 10000:
                        break
                    page += 1
                    pct = min(60, 30 + page * 5)
                    await cb("progress_txns", pct, count=tx_count)
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"ETH txlist fetch error: {e}")
            return total_in, total_out, tx_count, yearly_stats

        async def fetch_tokentx() -> dict:
            await cb("progress_tokens", 70)
            try:
                address_lower = address.lower()
                page = 1
                for _ in range(10): # Max 10 sahifa
                    resp = await safe_request(
                        client, "GET", _BASE_URL,
                        params={
                            "module": "account",
                            "action": "tokentx",
                            "address": address,
                            "startblock": "0",
                            "endblock": "99999999",
                            "sort": "desc",
                            "offset": "10000",
                            "page": str(page),
                            "apikey": ETHERSCAN_API_KEY,
                        },
                    )
                    token_resp_data = resp.json()
                    token_txs = token_resp_data.get("result", [])

                    if not isinstance(token_txs, list) or not token_txs:
                        break

                    for ttx in token_txs:
                        symbol = ttx.get("tokenSymbol", "UNKNOWN")
                        decimals = int(ttx.get("tokenDecimal", "18"))
                        value_raw = int(ttx.get("value", "0"))
                        value_token = value_raw / (10 ** decimals)

                        if symbol not in token_data_map:
                            token_data_map[symbol] = {"income": 0.0, "outcome": 0.0}

                        if ttx.get("to", "").lower() == address_lower:
                            token_data_map[symbol]["income"] += value_token
                        if ttx.get("from", "").lower() == address_lower:
                            token_data_map[symbol]["outcome"] += value_token
                            
                    if len(token_txs) < 10000:
                        break
                    page += 1
                    pct = min(95, 70 + page * 5)
                    await cb("progress_token_history", pct, symbol="ERC-20")
                    await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"ETH token fetch error: {e}")
            return token_data_map

        # ═══ Parallel Fetching ═══
        results = await asyncio.gather(
            fetch_balance(),
            fetch_txlist(),
            fetch_tokentx(),
            return_exceptions=True
        )

        balance_data = results[0]
        txlist_data = results[1]
        tokentx_data = results[2]

        if isinstance(balance_data, Exception):
            logger.error(f"ETH balance fetch error: {balance_data}")
            return {"network": "ETH", "address": address, "error": str(balance_data)}

        # 1. Hozirgi ETH balansi
        try:
            current_balance = int(balance_data.get("result", "0")) / _WEI_DIVISOR
        except Exception as e:
            logger.error(f"Error parsing ETH balance: {e}")
            return {"network": "ETH", "address": address, "error": str(e)}

    await cb("progress_finalizing", 98)

    income_eth: float = total_in / _WEI_DIVISOR
    outcome_eth: float = total_out / _WEI_DIVISOR
    total_volume: float = income_eth + outcome_eth

    # Token guruhlash
    tokens: list[dict[str, str]] = []
    for symbol in sorted(token_data_map.keys()):
        inc: float = token_data_map[symbol]["income"]
        out: float = token_data_map[symbol]["outcome"]
        vol: float = inc + out
        net: float = inc - out

        if vol < 0.0001:
            continue

        tokens.append({
            "symbol": symbol,
            "income": f"{inc:,.4f}",
            "outcome": f"{out:,.4f}",
            "net": f"{net:,.4f}",
            "volume": f"{vol:,.4f}",
            "current_balance": "—",
        })

    return {
        "network": "ETH",
        "address": address,
        "current_balance": f"{current_balance:,.6f} ETH",
        "total_income": f"{income_eth:,.6f} ETH",
        "total_outcome": f"{outcome_eth:,.6f} ETH",
        "net_balance": f"{income_eth - outcome_eth:,.6f} ETH",
        "total_volume": f"{total_volume:,.6f} ETH",
        "tx_count": tx_count,
        "tokens": tokens,
        "yearly_stats": yearly_stats,
    }
