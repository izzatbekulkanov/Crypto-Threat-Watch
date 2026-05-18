"""Ethereum tarmog'i — Professional audit xizmati (etherscan.io)."""

import httpx
import logging

from config import ETHERSCAN_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.etherscan.io/api"
_WEI_DIVISOR: int = 10**18


async def get_eth_balance(address: str) -> dict:
    """Ethereum hamyon to'liq professional audit.

    - Hozirgi ETH balansi (real-time)
    - ETH kirim/chiqim/sof qoldiq
    - Jami tranzaksiyalar hajmi
    - ERC-20 tokenlar bo'yicha guruhlash (har bir token alohida)
    - Tranzaksiyalar soni

    Args:
        address: Ethereum hamyon manzili (0x...).

    Returns:
        To'liq audit natijasi.
    """
    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    current_balance: float = 0.0

    # ERC-20 tokenlar
    token_data_map: dict[str, dict[str, float]] = {}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # 1. Hozirgi ETH balansi
        try:
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
            balance_data: dict = resp.json()
            current_balance = int(balance_data.get("result", "0")) / _WEI_DIVISOR
        except Exception as e:
            logger.error(f"ETH balance fetch error: {e}")
            return {"network": "ETH", "address": address, "error": str(e)}

        # 2. ETH tranzaksiyalari (yillar kesimida)
        try:
            address_lower: str = address.lower()
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
                data: dict = resp.json()
                transactions: list[dict] = data.get("result", [])

                if not isinstance(transactions, list) or not transactions:
                    break

                tx_count += len(transactions)

                for tx in transactions:
                    value: int = int(tx.get("value", "0"))
                    if value == 0:
                        continue
                    if tx.get("to", "").lower() == address_lower:
                        total_in += value
                    if tx.get("from", "").lower() == address_lower:
                        total_out += value
                
                if len(transactions) < 10000:
                    break
                page += 1

        except Exception as e:
            logger.warning(f"ETH txlist fetch error: {e}")

        # 3. ERC-20 token transferlari
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
                token_resp_data: dict = resp.json()
                token_txs: list[dict] = token_resp_data.get("result", [])

                if not isinstance(token_txs, list) or not token_txs:
                    break

                for ttx in token_txs:
                    symbol: str = ttx.get("tokenSymbol", "UNKNOWN")
                    decimals: int = int(ttx.get("tokenDecimal", "18"))
                    value_raw: int = int(ttx.get("value", "0"))
                    value_token: float = value_raw / (10 ** decimals)

                    if symbol not in token_data_map:
                        token_data_map[symbol] = {"income": 0.0, "outcome": 0.0}

                    if ttx.get("to", "").lower() == address_lower:
                        token_data_map[symbol]["income"] += value_token
                    if ttx.get("from", "").lower() == address_lower:
                        token_data_map[symbol]["outcome"] += value_token
                        
                if len(token_txs) < 10000:
                    break
                page += 1

        except Exception as e:
            logger.warning(f"ETH token fetch error: {e}")

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
    }
