"""TRON tarmog'i — Professional audit xizmati (TronGrid)."""

import httpx
import logging

from config import TRONGRID_API_KEY
from services import safe_request, DEFAULT_TIMEOUT

logger: logging.Logger = logging.getLogger(__name__)

_BASE_URL: str = "https://api.trongrid.io"
_USDT_CONTRACT: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
_TRX_DIVISOR: int = 10**6


async def get_tron_usdt_balance(address: str) -> dict:
    """TRON hamyon to'liq professional audit.

    - Hozirgi TRX balansi (real-time)
    - TRX kirim/chiqim
    - USDT (TRC-20) kirim/chiqim
    - Boshqa TRC-20 tokenlar bo'yicha guruhlash
    - Jami tranzaksiyalar hajmi
    - Tranzaksiyalar soni

    Args:
        address: TRON hamyon manzili (T...).

    Returns:
        To'liq audit natijasi.
    """
    trx_in: int = 0
    trx_out: int = 0
    trx_tx_count: int = 0
    current_trx: float = 0.0

    # TRC-20 tokenlar
    token_data_map: dict[str, dict[str, float]] = {}

    headers: dict[str, str] = {"TRON-PRO-API-KEY": TRONGRID_API_KEY}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # 1. Hozirgi TRX balansi
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
        try:
            fingerprint = None
            for _ in range(50): # Max 10,000 txs
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
                    
                trx_tx_count += len(trx_txs)

                for tx in trx_txs:
                    raw_data: dict = tx.get("raw_data", {})
                    contracts: list = raw_data.get("contract", [])
                    for contract in contracts:
                        if contract.get("type") == "TransferContract":
                            param: dict = contract.get("parameter", {}).get("value", {})
                            amount: int = param.get("amount", 0)
                            to_addr: str = param.get("to_address", "")
                            owner_addr: str = param.get("owner_address", "")

                            if _is_same_address(to_addr, address):
                                trx_in += amount
                            if _is_same_address(owner_addr, address):
                                trx_out += amount
                                
                fingerprint = trx_data.get("meta", {}).get("fingerprint")
                if not fingerprint:
                    break
        except Exception as e:
            logger.warning(f"TRON TRX transactions error: {e}")

        # 3. TRC-20 token tranzaksiyalari (yillar kesimida)
        try:
            address_lower: str = address.lower()
            fingerprint = None
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

                    if symbol not in token_data_map:
                        token_data_map[symbol] = {"income": 0.0, "outcome": 0.0}

                    to_addr_str: str = tx.get("to", "").lower()
                    from_addr_str: str = tx.get("from", "").lower()

                    if to_addr_str == address_lower:
                        token_data_map[symbol]["income"] += token_value
                    if from_addr_str == address_lower:
                        token_data_map[symbol]["outcome"] += token_value
                        
                fingerprint = trc20_data.get("meta", {}).get("fingerprint")
                if not fingerprint:
                    break
        except Exception as e:
            logger.warning(f"TRON TRC-20 fetch error: {e}")

    # Hisoblash
    income_trx: float = trx_in / _TRX_DIVISOR
    outcome_trx: float = trx_out / _TRX_DIVISOR
    volume_trx: float = income_trx + outcome_trx

    # USDT ni asosiy ko'rsatkich sifatida olish
    usdt_data: dict[str, float] = token_data_map.get("USDT", {"income": 0.0, "outcome": 0.0})
    usdt_income: float = usdt_data["income"]
    usdt_outcome: float = usdt_data["outcome"]
    usdt_volume: float = usdt_income + usdt_outcome

    # Token guruhlash
    tokens: list[dict[str, str]] = []

    # TRX birinchi
    tokens.append({
        "symbol": "TRX",
        "current_balance": f"{current_trx:,.4f}",
        "income": f"{income_trx:,.4f}",
        "outcome": f"{outcome_trx:,.4f}",
        "net": f"{income_trx - outcome_trx:,.4f}",
        "volume": f"{volume_trx:,.4f}",
    })

    # Boshqa tokenlar
    for symbol in sorted(token_data_map.keys()):
        inc: float = token_data_map[symbol]["income"]
        out: float = token_data_map[symbol]["outcome"]
        vol: float = inc + out
        net: float = inc - out

        if vol < 0.001:
            continue

        tokens.append({
            "symbol": symbol,
            "current_balance": "—",
            "income": f"{inc:,.4f}",
            "outcome": f"{out:,.4f}",
            "net": f"{net:,.4f}",
            "volume": f"{vol:,.4f}",
        })

    # Asosiy ko'rsatkich — USDT bo'lsa USDT, bo'lmasa TRX
    if usdt_volume > 0:
        main_income: str = f"{usdt_income:,.4f} USDT"
        main_outcome: str = f"{usdt_outcome:,.4f} USDT"
        main_net: str = f"{usdt_income - usdt_outcome:,.4f} USDT"
        main_volume: str = f"{usdt_volume:,.4f} USDT"
    else:
        main_income = f"{income_trx:,.4f} TRX"
        main_outcome = f"{outcome_trx:,.4f} TRX"
        main_net = f"{income_trx - outcome_trx:,.4f} TRX"
        main_volume = f"{volume_trx:,.4f} TRX"

    total_tx: int = trx_tx_count + len(token_data_map.get("USDT", {}).keys())

    return {
        "network": "TRON",
        "address": address,
        "current_balance": f"{current_trx:,.4f} TRX",
        "total_income": main_income,
        "total_outcome": main_outcome,
        "net_balance": main_net,
        "total_volume": main_volume,
        "tx_count": trx_tx_count,
        "tokens": tokens,
    }


def _is_same_address(hex_or_base58: str, target_base58: str) -> bool:
    """Manzillarni solishtirish."""
    if not hex_or_base58 or not target_base58:
        return False
    return hex_or_base58 == target_base58 or hex_or_base58.lower() == target_base58.lower()
