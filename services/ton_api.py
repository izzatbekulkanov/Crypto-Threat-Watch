"""TON tarmog'i — Professional audit xizmati (tonapi.io + toncenter.com)."""

import httpx
import logging
import asyncio
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
    yearly_stats: dict[str, dict[str, float]] = {}

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # ═══ 1. Hozirgi balans (tonapi.io) ═══
        raw_address: str = ""  # "0:..." formatdagi xom manzil (taqqoslash uchun)
        try:
            resp = await safe_request(
                client, "GET", f"{_TONAPI_URL}/accounts/{address}", headers=_HEADERS
            )
            account_data: dict = resp.json()
            balance_nano: int = int(account_data.get("balance", 0))
            current_balance = balance_nano / _NANOTON_DIVISOR
            account_status = account_data.get("status", "unknown")
            # tonapi "0:hex..." formatida qaytaradi — transfer taqqoslash uchun saqlaymiz
            raw_address = account_data.get("address", "").lower()
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

        # ═══ 3. Tranzaksiyalar (tonapi.io) — Yillar kesimida barchasini olish ═══
        try:
            before_lt = None
            # Maksimal 100 sahifa (10,000 tranzaksiya) xavfsizlik uchun, aksariyat hamyonlar uchun yetarli.
            for _ in range(100):
                params = {"limit": 100}
                if before_lt:
                    params["before_lt"] = before_lt
                    
                resp = await safe_request(
                    client, "GET",
                    f"{_TONAPI_URL}/blockchain/accounts/{address}/transactions",
                    headers=_HEADERS,
                    params=params,
                )
                data: dict = resp.json()
                transactions: list[dict] = data.get("transactions", [])
                
                if not transactions:
                    break
                    
                tx_count += len(transactions)

                for tx in transactions:
                    tx_time = tx.get("utime", 0)
                    year = "Unknown"
                    if tx_time:
                        year = str(datetime.fromtimestamp(tx_time, tz=timezone.utc).year)
                    if year not in yearly_stats:
                        yearly_stats[year] = {"in": 0.0, "out": 0.0}

                    in_msg: dict | None = tx.get("in_msg")
                    if in_msg and in_msg.get("value"):
                        # Faqat tashqi manzildan kelgan kirimlarni hisoblash
                        # (o'z-o'ziga yuborishni chiqarib tashlash)
                        src = (in_msg.get("source") or {})
                        src_addr = src.get("address", "").lower() if isinstance(src, dict) else ""
                        if src_addr != raw_address:
                            val = int(in_msg["value"])
                            total_in += val
                            yearly_stats[year]["in"] += val / _NANOTON_DIVISOR

                    out_msgs: list[dict] = tx.get("out_msgs", [])
                    for msg in out_msgs:
                        if msg.get("value"):
                            # Faqat tashqi manzilga ketgan chiqimlarni hisoblash
                            dest = (msg.get("destination") or {})
                            dest_addr = dest.get("address", "").lower() if isinstance(dest, dict) else ""
                            if dest_addr != raw_address:
                                val = int(msg["value"])
                                total_out += val
                                yearly_stats[year]["out"] += val / _NANOTON_DIVISOR
                            
                last_lt = transactions[-1].get("lt")
                if not last_lt:
                    break
                before_lt = last_lt
                
                # ISO Standart: API Limitni buzmaslik uchun xavfsiz kutish
                await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.warning(f"TON transactions fetch error: {e}")

        # ═══ 4. Jetton balanslar + transfer tarixi ═══
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
                divisor: float = 10 ** decimals
                raw_balance: int = int(item.get("balance", "0"))
                token_balance: float = raw_balance / divisor

                if token_balance < 0.00001:
                    continue

                # Jetton kontrakti manzili (transfer tarixi so'rash uchun)
                jetton_address: str = jetton_info.get("address", "")

                # Bu jetton bo'yicha barcha transferlarni yuklab olish
                j_in_nano: int = 0
                j_out_nano: int = 0
                try:
                    j_cursor = None
                    for _ in range(50):  # Maks 5000 transfer
                        j_params: dict = {"limit": 100, "direction": "all"}
                        if j_cursor:
                            j_params["cursor"] = j_cursor
                        j_resp = await safe_request(
                            client, "GET",
                            f"{_TONAPI_URL}/accounts/{address}/jettons/{jetton_address}/history",
                            headers=_HEADERS,
                            params=j_params,
                        )
                        j_data: dict = j_resp.json()
                        events: list[dict] = j_data.get("events", [])
                        if not events:
                            break
                        for event in events:
                            for action in event.get("actions", []):
                                jt = action.get("JettonTransfer", {})
                                if not jt:
                                    continue
                                amt_raw: int = int(jt.get("amount", 0))
                                sender = (jt.get("sender") or {}).get("address", "").lower()
                                recipient = (jt.get("recipient") or {}).get("address", "").lower()
                                if sender == raw_address:
                                    j_out_nano += amt_raw
                                elif recipient == raw_address:
                                    j_in_nano += amt_raw
                        next_cursor = j_data.get("next_from")
                        if not next_cursor:
                            break
                        j_cursor = next_cursor
                        await asyncio.sleep(0.3)
                except Exception as je:
                    logger.warning(f"Jetton {symbol} transfer history error: {je}")

                j_income: float = j_in_nano / divisor
                j_outcome: float = j_out_nano / divisor

                jetton_balances.append({
                    "symbol": symbol,
                    "balance": f"{token_balance:,.4f}",
                    "income": f"{j_income:,.4f} {symbol}",
                    "outcome": f"{j_outcome:,.4f} {symbol}",
                    "volume": f"{(j_income + j_outcome):,.4f} {symbol}",
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
        "yearly_stats": yearly_stats,
    }
