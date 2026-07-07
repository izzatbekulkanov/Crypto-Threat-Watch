"""Ethereum va EVM L2 tarmoqlari — Multi-Chain professional audit xizmati."""

import httpx
import logging
import asyncio
import re
from datetime import datetime, timezone
from typing import Awaitable, Callable

from config import (
    ETHERSCAN_API_KEY,
    BSCSCAN_API_KEY,
    POLYGONSCAN_API_KEY,
    BASESCAN_API_KEY
)
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

ProgressCb = Callable[..., Awaitable[None]]


async def _noop_progress(*args, **kwargs) -> None:
    return None


async def fetch_chain_data(
    client: httpx.AsyncClient,
    chain_name: str,
    base_url: str,
    api_key: str,
    address: str,
    is_etherscan_v2: bool = False,
    is_blockscout: bool = False,
) -> dict:
    """Belgilangan EVM tarmog'idan balans, tranzaksiyalar va token o'tkazmalarini oladi."""
    if not is_blockscout and not api_key:
        logger.info(f"Skipping {chain_name} query: API key not configured in .env.")
        return {"balance": 0.0, "transfers": []}

    balance = 0.0
    transfers = []
    address_lower = address.lower()

    # 1. Native Balans
    try:
        params = {
            "module": "account",
            "action": "balance",
            "address": address,
            "tag": "latest",
        }
        if api_key and not is_blockscout:
            params["apikey"] = api_key
        if is_etherscan_v2:
            if chain_name == "Ethereum":
                params["chainid"] = "1"
            elif chain_name == "BSC":
                params["chainid"] = "56"
        
        resp = await safe_request(client, "GET", base_url, params=params)
        balance_data = resp.json()
        result_str = balance_data.get("result", "0")
        if result_str and result_str.isdigit():
            balance = int(result_str) / (10**18)
        else:
            err_msg = balance_data.get("result", "")
            if "Free API access" in str(err_msg) or "NOTOK" in str(balance_data.get("message", "")):
                logger.warning(f"{chain_name} balance API returned warning: {balance_data}")
    except Exception as e:
        logger.error(f"{chain_name} balance fetch error: {e}")

    # 2. Native tranzaksiyalar (txlist)
    try:
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": "0",
            "endblock": "99999999",
            "sort": "desc",
            "offset": "1000",
            "page": "1",
        }
        if api_key and not is_blockscout:
            params["apikey"] = api_key
        if is_etherscan_v2:
            if chain_name == "Ethereum":
                params["chainid"] = "1"
            elif chain_name == "BSC":
                params["chainid"] = "56"
        
        resp = await safe_request(client, "GET", base_url, params=params)
        data = resp.json()
        txs = data.get("result", [])
        if isinstance(txs, list):
            native_symbol = "BNB" if chain_name == "BSC" else ("MATIC" if chain_name == "Polygon" else "ETH")
            for tx in txs:
                value_str = tx.get("value", "0")
                if not value_str or not value_str.isdigit():
                    continue
                value = int(value_str)
                if value == 0:
                    continue

                tx_time = int(tx.get("timeStamp", "0"))
                tx_hash = tx.get("hash", "")
                sender = tx.get("from", "").lower()
                recipient = tx.get("to", "").lower()

                if sender == address_lower and recipient == address_lower:
                    continue

                if recipient == address_lower:
                    transfers.append({
                        "tx_hash": tx_hash,
                        "timestamp": tx_time,
                        "symbol": native_symbol,
                        "amount": value / (10**18),
                        "direction": "in",
                        "counterparty": sender,
                        "chain": chain_name
                    })
                elif sender == address_lower:
                    transfers.append({
                        "tx_hash": tx_hash,
                        "timestamp": tx_time,
                        "symbol": native_symbol,
                        "amount": value / (10**18),
                        "direction": "out",
                        "counterparty": recipient,
                        "chain": chain_name
                    })
    except Exception as e:
        logger.warning(f"{chain_name} txlist fetch error: {e}")

    # 3. ERC-20 token tranzaksiyalari (tokentx)
    try:
        params = {
            "module": "account",
            "action": "tokentx",
            "address": address,
            "startblock": "0",
            "endblock": "99999999",
            "sort": "desc",
            "offset": "1000",
            "page": "1",
        }
        if api_key and not is_blockscout:
            params["apikey"] = api_key
        if is_etherscan_v2:
            if chain_name == "Ethereum":
                params["chainid"] = "1"
            elif chain_name == "BSC":
                params["chainid"] = "56"

        resp = await safe_request(client, "GET", base_url, params=params)
        data = resp.json()
        token_txs = data.get("result", [])
        if isinstance(token_txs, list):
            for ttx in token_txs:
                symbol = ttx.get("tokenSymbol", "UNKNOWN")
                decimals_str = ttx.get("tokenDecimal", "18")
                decimals = int(decimals_str) if decimals_str and decimals_str.isdigit() else 18
                value_str = ttx.get("value", "0")
                if not value_str or not value_str.isdigit():
                    continue
                value_raw = int(value_str)
                value_token = value_raw / (10**decimals)
                tx_time = int(ttx.get("timeStamp", "0"))
                tx_hash = ttx.get("hash", "")
                sender = ttx.get("from", "").lower()
                recipient = ttx.get("to", "").lower()

                if sender == address_lower and recipient == address_lower:
                    continue

                display_symbol = f"{symbol} ({chain_name})" if chain_name != "Ethereum" else symbol
                if recipient == address_lower:
                    transfers.append({
                        "tx_hash": tx_hash,
                        "timestamp": tx_time,
                        "symbol": display_symbol,
                        "amount": value_token,
                        "direction": "in",
                        "counterparty": sender,
                        "chain": chain_name
                    })
                elif sender == address_lower:
                    transfers.append({
                        "tx_hash": tx_hash,
                        "timestamp": tx_time,
                        "symbol": display_symbol,
                        "amount": value_token,
                        "direction": "out",
                        "counterparty": recipient,
                        "chain": chain_name
                    })
    except Exception as e:
        logger.warning(f"{chain_name} token fetch error: {e}")

    return {"balance": balance, "transfers": transfers}


async def get_eth_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """EVM hamyon to'liq professional multi-chain auditi."""
    cb: ProgressCb = progress or _noop_progress

    await cb("progress_balance", 5)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # Tarmoqlar so'rovlarini parallel ravishda ishga tushiramiz
        tasks = []
        
        # 1. Ethereum Mainnet (Etherscan V2 - bepul API kalit bilan ishlaydi)
        tasks.append(fetch_chain_data(
            client=client,
            chain_name="Ethereum",
            base_url="https://api.etherscan.io/v2/api",
            api_key=ETHERSCAN_API_KEY,
            address=address,
            is_etherscan_v2=True
        ))

        # 2. BSC (Etherscan V2 - faqat pullik tarifda bepul skanerlaydi, agar kalit sozlangan bo'lsa)
        if BSCSCAN_API_KEY:
            tasks.append(fetch_chain_data(
                client=client,
                chain_name="BSC",
                base_url="https://api.etherscan.io/v2/api",
                api_key=BSCSCAN_API_KEY,
                address=address,
                is_etherscan_v2=True
            ))
        else:
            logger.info("BSC scanning skipped: BSCSCAN_API_KEY is not configured in .env.")

        # 3. Polygon (Blockscout - 100% BEPUL, API kalit talab etilmaydi!)
        tasks.append(fetch_chain_data(
            client=client,
            chain_name="Polygon",
            base_url="https://polygon.blockscout.com/api",
            api_key="",
            address=address,
            is_blockscout=True
        ))

        # 4. Base (Blockscout - 100% BEPUL, API kalit talab etilmaydi!)
        tasks.append(fetch_chain_data(
            client=client,
            chain_name="Base",
            base_url="https://base.blockscout.com/api",
            api_key="",
            address=address,
            is_blockscout=True
        ))

        await cb("progress_txns", 30)
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Natijalarni tahlil qilish
    eth_result = {"balance": 0.0, "transfers": []}
    bsc_result = {"balance": 0.0, "transfers": []}
    poly_result = {"balance": 0.0, "transfers": []}
    base_result = {"balance": 0.0, "transfers": []}

    idx = 0
    # Ethereum always exists in tasks
    if idx < len(results) and not isinstance(results[idx], Exception):
        eth_result = results[idx]
    idx += 1

    # BSC exists only if BSCSCAN_API_KEY is configured
    if BSCSCAN_API_KEY:
        if idx < len(results) and not isinstance(results[idx], Exception):
            bsc_result = results[idx]
        idx += 1

    # Polygon always exists
    if idx < len(results) and not isinstance(results[idx], Exception):
        poly_result = results[idx]
    idx += 1

    # Base always exists
    if idx < len(results) and not isinstance(results[idx], Exception):
        base_result = results[idx]
    idx += 1

    # Balanslar
    eth_balance = eth_result.get("balance", 0.0)
    bsc_balance = bsc_result.get("balance", 0.0)
    poly_balance = poly_result.get("balance", 0.0)
    base_balance = base_result.get("balance", 0.0)

    # Barcha o'tkazmalarni jamlash
    all_transfers = []
    all_transfers.extend(eth_result.get("transfers", []))
    all_transfers.extend(bsc_result.get("transfers", []))
    all_transfers.extend(poly_result.get("transfers", []))
    all_transfers.extend(base_result.get("transfers", []))

    # Vaqt bo'yicha saralash
    all_transfers.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

    await cb("progress_finalizing", 90)

    # Swaplarni aniqlash va ajratish
    from utils import process_transfers_and_detect_swaps
    normal_transfers, swaps = process_transfers_and_detect_swaps(all_transfers)

    # Aktivlar bo'yicha statistika hisoblash
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

    # Yillik statistika (faqat native tangalar uchun)
    yearly_stats: dict[str, dict[str, float]] = {}
    for t in normal_transfers:
        if t["symbol"] in ["ETH", "BNB", "MATIC", "ETH (Base)"]:
            year = "Unknown"
            if t["timestamp"]:
                year = str(datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).year)
            if year not in yearly_stats:
                yearly_stats[year] = {"in": 0.0, "out": 0.0}
            if t["direction"] == "in":
                yearly_stats[year]["in"] += t["amount"]
            else:
                yearly_stats[year]["out"] += t["amount"]

    # Balans ko'rinishi
    balance_parts = []
    if eth_balance > 0 or (bsc_balance == 0 and poly_balance == 0 and base_balance == 0):
        balance_parts.append(f"{eth_balance:,.6f} ETH")
    if bsc_balance > 0:
        balance_parts.append(f"{bsc_balance:,.4f} BNB")
    if poly_balance > 0:
        balance_parts.append(f"{poly_balance:,.4f} MATIC")
    if base_balance > 0:
        balance_parts.append(f"{base_balance:,.6f} ETH (Base)")
    current_balance_str = " + ".join(balance_parts) if balance_parts else "0.0000 ETH"

    # Aktivlar ro'yxatini to'ldirish
    assets: list[dict] = []
    
    # 1. Native ETH (Ethereum)
    eth_s = token_stats.get("ETH", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    if eth_balance > 0 or eth_s["tx_count"] > 0 or not token_stats:
        assets.append({
            "symbol": "ETH",
            "is_native": True,
            "balance": f"{eth_balance:,.6f} ETH",
            "income": f"{eth_s['income']:,.6f} ETH",
            "outcome": f"{eth_s['outcome']:,.6f} ETH",
            "net": f"{eth_s['income'] - eth_s['outcome']:,.6f} ETH",
            "volume": f"{eth_s['income'] + eth_s['outcome']:,.6f} ETH",
            "tx_count": eth_s["tx_count"],
        })

    # 2. Native BNB (BSC)
    bnb_s = token_stats.get("BNB", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    if bsc_balance > 0 or bnb_s["tx_count"] > 0:
        assets.append({
            "symbol": "BNB",
            "is_native": True,
            "balance": f"{bsc_balance:,.4f} BNB",
            "income": f"{bnb_s['income']:,.4f} BNB",
            "outcome": f"{bnb_s['outcome']:,.4f} BNB",
            "net": f"{bnb_s['income'] - bnb_s['outcome']:,.4f} BNB",
            "volume": f"{bnb_s['income'] + bnb_s['outcome']:,.4f} BNB",
            "tx_count": bnb_s["tx_count"],
        })

    # 3. Native MATIC (Polygon)
    matic_s = token_stats.get("MATIC", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    if poly_balance > 0 or matic_s["tx_count"] > 0:
        assets.append({
            "symbol": "MATIC",
            "is_native": True,
            "balance": f"{poly_balance:,.4f} MATIC",
            "income": f"{matic_s['income']:,.4f} MATIC",
            "outcome": f"{matic_s['outcome']:,.4f} MATIC",
            "net": f"{matic_s['income'] - matic_s['outcome']:,.4f} MATIC",
            "volume": f"{matic_s['income'] + matic_s['outcome']:,.4f} MATIC",
            "tx_count": matic_s["tx_count"],
        })

    # 4. Native ETH (Base)
    base_eth_s = token_stats.get("ETH (Base)", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    if base_balance > 0 or base_eth_s["tx_count"] > 0:
        assets.append({
            "symbol": "ETH (Base)",
            "is_native": True,
            "balance": f"{base_balance:,.6f} ETH (Base)",
            "income": f"{base_eth_s['income']:,.6f} ETH (Base)",
            "outcome": f"{base_eth_s['outcome']:,.6f} ETH (Base)",
            "net": f"{base_eth_s['income'] - base_eth_s['outcome']:,.6f} ETH (Base)",
            "volume": f"{base_eth_s['income'] + base_eth_s['outcome']:,.6f} ETH (Base)",
            "tx_count": base_eth_s["tx_count"],
        })

    # Boshqa ERC-20 tokenlar
    for symbol in sorted(token_stats.keys()):
        if symbol in ["ETH", "BNB", "MATIC", "ETH (Base)"]:
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

    grand_tx_count = len(normal_transfers)
    asset_count = len(assets)

    # Legacy variables compatibility
    income_eth = eth_s["income"]
    outcome_eth = eth_s["outcome"]
    volume_eth = income_eth + outcome_eth

    return {
        "network": "EVM Multi-Chain",
        "address": address,
        "current_balance": current_balance_str,
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
    }
