"""Ethereum tarmog'i — Professional audit xizmati (etherscan.io)."""

import httpx
import logging
import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import ETHERSCAN_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.etherscan.io/v2/api"
_WEI_DIVISOR: int = 10**18

ProgressCb = Callable[..., Awaitable[None]]


async def _noop_progress(*args, **kwargs) -> None:
    return None


async def get_eth_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """Ethereum hamyon to'liq professional audit."""
    cb: ProgressCb = progress or _noop_progress

    current_balance: float = 0.0
    address_lower = address.lower()
    transfers: list[dict] = []

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # 1. Hozirgi ETH balansi
        await cb("progress_balance", 5)
        try:
            resp = await safe_request(
                client, "GET", _BASE_URL,
                params={
                    "chainid": "1",
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest",
                    "apikey": ETHERSCAN_API_KEY,
                },
            )
            balance_data: dict = resp.json()
            current_balance = int(balance_data.get("result", "0")) / _WEI_DIVISOR
        except Exception as e:
            logger.error(f"ETH balance fetch error: {e}")
            return {"network": "ETH", "address": address, "error": str(e)}

        # 2. ETH tranzaksiyalari
        await cb("progress_txns", 15, count=0)
        try:
            page = 1
            for _ in range(10):  # Max 10 sahifa (100,000 tranzaksiya)
                resp = await safe_request(
                    client, "GET", _BASE_URL,
                    params={
                        "chainid": "1",
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
                data: dict = resp.json()
                transactions: list[dict] = data.get("result", [])

                if not isinstance(transactions, list) or not transactions:
                    break

                for tx in transactions:
                    value: int = int(tx.get("value", "0"))
                    if value == 0:
                        continue

                    tx_time = int(tx.get("timeStamp", "0"))
                    tx_hash = tx.get("hash", "")
                    sender = tx.get("from", "").lower()
                    recipient = tx.get("to", "").lower()

                    if sender == address_lower and recipient == address_lower:
                        # Self-transferlar hisobga olinmaydi
                        continue

                    if recipient == address_lower:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": "ETH",
                            "amount": value / _WEI_DIVISOR,
                            "direction": "in",
                            "counterparty": sender
                        })
                    elif sender == address_lower:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": "ETH",
                            "amount": value / _WEI_DIVISOR,
                            "direction": "out",
                            "counterparty": recipient
                        })

                if len(transactions) < 10000:
                    break
                page += 1
                pct = min(50, 15 + page * 5)
                await cb("progress_txns", pct, count=len(transfers))
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"ETH txlist fetch error: {e}")

        # 3. ERC-20 token transferlari
        await cb("progress_tokens", 60)
        try:
            page = 1
            for _ in range(10):  # Max 10 sahifa
                resp = await safe_request(
                    client, "GET", _BASE_URL,
                    params={
                        "chainid": "1",
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
                token_resp_data: dict = resp.json()
                token_txs: list[dict] = token_resp_data.get("result", [])

                if not isinstance(token_txs, list) or not token_txs:
                    break

                for ttx in token_txs:
                    symbol: str = ttx.get("tokenSymbol", "UNKNOWN")
                    decimals: int = int(ttx.get("tokenDecimal", "18"))
                    value_raw: int = int(ttx.get("value", "0"))
                    value_token: float = value_raw / (10 ** decimals)
                    tx_time = int(ttx.get("timeStamp", "0"))
                    tx_hash = ttx.get("hash", "")
                    sender = ttx.get("from", "").lower()
                    recipient = ttx.get("to", "").lower()

                    if sender == address_lower and recipient == address_lower:
                        continue

                    if recipient == address_lower:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": symbol,
                            "amount": value_token,
                            "direction": "in",
                            "counterparty": sender
                        })
                    elif sender == address_lower:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": symbol,
                            "amount": value_token,
                            "direction": "out",
                            "counterparty": recipient
                        })

                if len(token_txs) < 10000:
                    break
                page += 1
                pct = min(95, 60 + page * 5)
                await cb("progress_token_history", pct, symbol="ERC-20")
                await asyncio.sleep(0.5)

        except Exception as e:
            logger.warning(f"ETH token fetch error: {e}")

    await cb("progress_finalizing", 98)

    # ═══ 4. Swaplarni aniqlash va ajratish ═══
    from utils import process_transfers_and_detect_swaps
    normal_transfers, swaps = process_transfers_and_detect_swaps(transfers)

    # ═══ 5. Aktivlar statistikasini hisoblash ═══
    token_stats: dict[str, dict] = {}
    for t in normal_transfers:
        sym = t["symbol"]
        if sym not in token_stats:
            token_stats[sym] = {"income": 0.0, "outcome": 0.0, "tx_count": 0}
        token_stats[sym]["tx_count"] += 1
        if t["direction"] == "in":
            token_stats[sym]["income"] += t["amount"]
        else:
            token_stats[sym]["outcome"] += t["amount"]

    # Yillik statistika (faqat normal native ETH uchun)
    yearly_stats: dict[str, dict[str, float]] = {}
    for t in normal_transfers:
        if t["symbol"] == "ETH":
            year = "Unknown"
            if t["timestamp"]:
                year = str(datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).year)
            if year not in yearly_stats:
                yearly_stats[year] = {"in": 0.0, "out": 0.0}
            if t["direction"] == "in":
                yearly_stats[year]["in"] += t["amount"]
            else:
                yearly_stats[year]["out"] += t["amount"]

    # ETH (Native) statistikalari
    eth_s = token_stats.get("ETH", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    income_eth = eth_s["income"]
    outcome_eth = eth_s["outcome"]
    volume_eth = income_eth + outcome_eth

    assets: list[dict] = []
    assets.append({
        "symbol": "ETH",
        "is_native": True,
        "balance": f"{current_balance:,.6f} ETH",
        "income": f"{income_eth:,.6f} ETH",
        "outcome": f"{outcome_eth:,.6f} ETH",
        "net": f"{income_eth - outcome_eth:,.6f} ETH",
        "volume": f"{volume_eth:,.6f} ETH",
        "tx_count": eth_s["tx_count"],
    })

    # ERC-20 tokenlar statistikalari
    for symbol in sorted(token_stats.keys()):
        if symbol == "ETH":
            continue

        j_stats = token_stats[symbol]
        j_income = j_stats["income"]
        j_outcome = j_stats["outcome"]
        j_volume = j_income + j_outcome
        j_net = j_income - j_outcome
        j_tx_count = j_stats["tx_count"]

        # Token hisoblangan balansi
        est_balance = max(0.0, j_net)

        assets.append({
            "symbol": symbol,
            "is_native": False,
            "balance": f"{est_balance:,.4f} {symbol}",
            "income": f"{j_income:,.4f} {symbol}",
            "outcome": f"{j_outcome:,.4f} {symbol}",
            "net": f"{j_net:,.4f} {symbol}",
            "volume": f"{j_volume:,.4f} {symbol}",
            "tx_count": j_tx_count,
        })

    grand_tx_count = len(normal_transfers)
    asset_count = len(assets)

    return {
        "network": "ETH",
        "address": address,
        "current_balance": f"{current_balance:,.6f} ETH",
        "total_income": f"{income_eth:,.6f} ETH",
        "total_outcome": f"{outcome_eth:,.6f} ETH",
        "net_balance": f"{income_eth - outcome_eth:,.6f} ETH",
        "total_volume": f"{volume_eth:,.6f} ETH",
        "tx_count": grand_tx_count,
        "assets": assets,
        "grand_tx_count": grand_tx_count,
        "asset_count": asset_count,
        "yearly_stats": yearly_stats,
        "swaps": swaps,
        "normal_transfers": normal_transfers,
        "tokens": [a for a in assets if not a["is_native"]],
    }
