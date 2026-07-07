"""TRON tarmog'i — Professional audit xizmati (TronGrid)."""

import httpx
import logging
import asyncio
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import TRONGRID_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.trongrid.io"
_USDT_CONTRACT: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
_TRX_DIVISOR: int = 10**6

ProgressCb = Callable[..., Awaitable[None]]


async def _noop_progress(*args, **kwargs) -> None:
    return None


async def get_tron_usdt_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """TRON hamyon to'liq professional audit."""
    cb: ProgressCb = progress or _noop_progress

    current_trx: float = 0.0
    transfers: list[dict] = []

    headers: dict[str, str] = {"TRON-PRO-API-KEY": TRONGRID_API_KEY}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # 1. Hozirgi TRX balansi
        await cb("progress_balance", 5)
        try:
            resp = await safe_request(
                client, "GET", f"{_BASE_URL}/v1/accounts/{address}", headers=headers
            )
            account_data: dict = resp.json()
            acc_list: list = account_data.get("data", [])
            if acc_list:
                current_trx = int(acc_list[0].get("balance", 0)) / _TRX_DIVISOR
        except Exception as e:
            logger.error(f"TRON account fetch error: {e}")
            return {"network": "TRON", "address": address, "error": str(e)}

        # 2. TRX tranzaksiyalari (yillar kesimida)
        await cb("progress_txns", 15, count=0)
        try:
            fingerprint = None
            page_idx = 0
            for _ in range(50):  # Max 10,000 txs
                params = {"only_confirmed": "true", "limit": "200"}
                if fingerprint:
                    params["fingerprint"] = fingerprint

                resp = await safe_request(
                    client, "GET",
                    f"{_BASE_URL}/v1/accounts/{address}/transactions",
                    headers=headers,
                    params=params,
                )
                trx_data: dict = resp.json()
                trx_txs: list[dict] = trx_data.get("data", [])

                if not trx_txs:
                    break

                for tx in trx_txs:
                    tx_time_ms = tx.get("block_timestamp", 0)
                    tx_time = int(tx_time_ms / 1000)
                    tx_hash = tx.get("txID", "")

                    raw_data: dict = tx.get("raw_data", {})
                    contracts: list = raw_data.get("contract", [])
                    for contract in contracts:
                        if contract.get("type") == "TransferContract":
                            param: dict = contract.get("parameter", {}).get("value", {})
                            amount: int = param.get("amount", 0)
                            to_addr: str = param.get("to_address", "")
                            owner_addr: str = param.get("owner_address", "")

                            # Self-transfer hisobga olinmaydi
                            if _is_same_address(to_addr, address) and _is_same_address(owner_addr, address):
                                continue

                            if _is_same_address(to_addr, address):
                                transfers.append({
                                    "tx_hash": tx_hash,
                                    "timestamp": tx_time,
                                    "symbol": "TRX",
                                    "amount": amount / _TRX_DIVISOR,
                                    "direction": "in",
                                    "counterparty": owner_addr
                                })
                            elif _is_same_address(owner_addr, address):
                                transfers.append({
                                    "tx_hash": tx_hash,
                                    "timestamp": tx_time,
                                    "symbol": "TRX",
                                    "amount": amount / _TRX_DIVISOR,
                                    "direction": "out",
                                    "counterparty": to_addr
                                })

                fingerprint = trx_data.get("meta", {}).get("fingerprint")
                if not fingerprint:
                    break

                page_idx += 1
                pct = min(50, 15 + page_idx * 3)
                await cb("progress_txns", pct, count=len(transfers))
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"TRON TRX transactions error: {e}")

        # 3. TRC-20 token tranzaksiyalari
        await cb("progress_tokens", 55)
        try:
            fingerprint = None
            trc_page_idx = 0
            for _ in range(50):
                params = {"only_confirmed": "true", "limit": "200"}
                if fingerprint:
                    params["fingerprint"] = fingerprint

                resp = await safe_request(
                    client, "GET",
                    f"{_BASE_URL}/v1/accounts/{address}/transactions/trc20",
                    headers=headers,
                    params=params,
                )
                trc20_data: dict = resp.json()
                trc20_txs: list[dict] = trc20_data.get("data", [])

                if not trc20_txs:
                    break

                for tx in trc20_txs:
                    value: int = int(tx.get("value", "0"))
                    if value == 0:
                        continue

                    token_info: dict = tx.get("token_info", {})
                    symbol: str = token_info.get("symbol", "UNKNOWN")
                    decimals: int = int(token_info.get("decimals", "6"))
                    token_value: float = value / (10 ** decimals)
                    tx_time_ms = tx.get("block_timestamp", 0)
                    tx_time = int(tx_time_ms / 1000)
                    tx_hash = tx.get("transaction_id", "")

                    to_addr_str: str = tx.get("to", "")
                    from_addr_str: str = tx.get("from", "")

                    if to_addr_str == address and from_addr_str == address:
                        continue

                    if to_addr_str == address:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": symbol,
                            "amount": token_value,
                            "direction": "in",
                            "counterparty": from_addr_str
                        })
                    elif from_addr_str == address:
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": symbol,
                            "amount": token_value,
                            "direction": "out",
                            "counterparty": to_addr_str
                        })

                fingerprint = trc20_data.get("meta", {}).get("fingerprint")
                if not fingerprint:
                    break
                trc_page_idx += 1
                pct = min(95, 55 + trc_page_idx * 4)
                await cb("progress_token_history", pct, symbol="TRC-20")
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(f"TRON TRC-20 fetch error: {e}")

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

    # Yillik statistika (faqat normal native TRX uchun)
    yearly_stats: dict[str, dict[str, float]] = {}
    for t in normal_transfers:
        if t["symbol"] == "TRX":
            year = "Unknown"
            if t["timestamp"]:
                year = str(datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).year)
            if year not in yearly_stats:
                yearly_stats[year] = {"in": 0.0, "out": 0.0}
            if t["direction"] == "in":
                yearly_stats[year]["in"] += t["amount"]
            else:
                yearly_stats[year]["out"] += t["amount"]

    # TRX (Native) statistikalari
    trx_s = token_stats.get("TRX", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    income_trx = trx_s["income"]
    outcome_trx = trx_s["outcome"]
    volume_trx = income_trx + outcome_trx

    assets: list[dict] = []
    assets.append({
        "symbol": "TRX",
        "is_native": True,
        "balance": f"{current_trx:,.4f} TRX",
        "income": f"{income_trx:,.4f} TRX",
        "outcome": f"{outcome_trx:,.4f} TRX",
        "net": f"{income_trx - outcome_trx:,.4f} TRX",
        "volume": f"{volume_trx:,.4f} TRX",
        "tx_count": trx_s["tx_count"],
    })

    # TRC-20 tokenlar statistikalari
    for symbol in sorted(token_stats.keys()):
        if symbol == "TRX":
            continue

        j_stats = token_stats[symbol]
        j_income = j_stats["income"]
        j_outcome = j_stats["outcome"]
        j_volume = j_income + j_outcome
        j_net = j_income - j_outcome
        j_tx_count = j_stats["tx_count"]

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

    # Asosiy ko'rsatkichlar (Dinamik tanlash, moslik uchun)
    usdt_stats = token_stats.get("USDT", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    usdt_income = usdt_stats["income"]
    usdt_outcome = usdt_stats["outcome"]
    usdt_volume = usdt_income + usdt_outcome

    if usdt_volume > 0:
        main_income = f"{usdt_income:,.4f} USDT"
        main_outcome = f"{usdt_outcome:,.4f} USDT"
        main_net = f"{usdt_income - usdt_outcome:,.4f} USDT"
        main_volume = f"{usdt_volume:,.4f} USDT"
    else:
        main_income = f"{income_trx:,.4f} TRX"
        main_outcome = f"{outcome_trx:,.4f} TRX"
        main_net = f"{income_trx - outcome_trx:,.4f} TRX"
        main_volume = f"{volume_trx:,.4f} TRX"

    grand_tx_count = len(normal_transfers)
    asset_count = len(assets)

    return {
        "network": "TRON",
        "address": address,
        "current_balance": f"{current_trx:,.4f} TRX",
        "total_income": main_income,
        "total_outcome": main_outcome,
        "net_balance": main_net,
        "total_volume": main_volume,
        "tx_count": grand_tx_count,
        "assets": assets,
        "grand_tx_count": grand_tx_count,
        "asset_count": asset_count,
        "yearly_stats": yearly_stats,
        "swaps": swaps,
        "normal_transfers": normal_transfers,
        "tokens": [a for a in assets if not a["is_native"]],
    }


def _is_same_address(hex_or_base58: str, target_base58: str) -> bool:
    """Manzillarni solishtirish."""
    if not hex_or_base58 or not target_base58:
        return False
    return hex_or_base58 == target_base58 or hex_or_base58.lower() == target_base58.lower()
