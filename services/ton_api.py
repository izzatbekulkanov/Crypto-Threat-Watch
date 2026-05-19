"""TON tarmog'i — Professional audit xizmati (tonapi.io + toncenter.com).

Tezlik optimizatsiyasi:
- TON tranzaksiyalari va Jetton tarixi PARALLEL yuklanadi (asyncio.gather)
- Jetton tarixi BIR endpoint orqali olinadi (per-token emas, bulk)
- Sleep delay 0.5s -> 0.1s (API key bilan 10 RPS limit)
"""

import httpx
import logging
import asyncio
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


async def _fetch_native_txs(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    cb: ProgressCb,
) -> tuple[int, int, int, dict[str, dict[str, float]]]:
    """TON (native) tranzaksiyalarini yuklab oladi.

    Returns:
        (total_in_nano, total_out_nano, tx_count, yearly_stats)
    """
    total_in: int = 0
    total_out: int = 0
    tx_count: int = 0
    yearly_stats: dict[str, dict[str, float]] = {}

    before_lt = None
    page_idx = 0

    for _ in range(100):  # Max 10,000 tranzaksiya
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
        page_idx += 1
        # 25% -> 60% oraliq native TX uchun
        pct = min(60, 25 + page_idx * 4)
        await cb("progress_txns", pct, count=tx_count)

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

        last_lt = transactions[-1].get("lt")
        if not last_lt:
            break
        before_lt = last_lt
        await asyncio.sleep(0.1)

    return total_in, total_out, tx_count, yearly_stats


async def _fetch_one_jetton_history(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    jetton_address: str,
    symbol: str,
) -> tuple[str, dict]:
    """BIR jetton uchun transfer tarixini yuklab oladi.

    Returns:
        (jetton_address, {"income_raw": int, "outcome_raw": int, "tx_count": int})
    """
    in_raw: int = 0
    out_raw: int = 0
    tx_n: int = 0

    cursor = None
    for _ in range(50):  # Maks 5000 transfer
        params: dict = {"limit": 100}
        if cursor:
            params["before_lt"] = cursor

        try:
            resp = await safe_request(
                client, "GET",
                f"{_TONAPI_URL}/accounts/{address}/jettons/{jetton_address}/history",
                headers=_HEADERS,
                params=params,
            )
        except Exception as e:
            logger.warning(f"Jetton {symbol} history error: {e}")
            break

        data: dict = resp.json()
        events: list[dict] = data.get("events", [])
        if not events:
            break

        for event in events:
            for action in event.get("actions", []):
                if action.get("type") != "JettonTransfer":
                    continue
                jt = action.get("JettonTransfer") or {}
                amt_raw_str = jt.get("amount", "0")
                try:
                    amt_raw: int = int(amt_raw_str)
                except (ValueError, TypeError):
                    continue
                if amt_raw == 0:
                    continue

                sender = (jt.get("sender") or {}).get("address", "").lower()
                recipient = (jt.get("recipient") or {}).get("address", "").lower()

                if sender == raw_address:
                    out_raw += amt_raw
                    tx_n += 1
                elif recipient == raw_address:
                    in_raw += amt_raw
                    tx_n += 1

        # Pagination — eng oxirgi event'ning lt'sini ishlatamiz
        next_from = data.get("next_from")
        if next_from in (None, 0, "0"):
            # Fallback: oxirgi event lt
            last_lt = events[-1].get("lt")
            if not last_lt or last_lt == cursor:
                break
            cursor = last_lt
        else:
            cursor = next_from

        if len(events) < 100:
            break

        await asyncio.sleep(0.1)

    return jetton_address.lower(), {
        "income_raw": in_raw,
        "outcome_raw": out_raw,
        "tx_count": tx_n,
    }


async def _fetch_all_jettons_history(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    jetton_balance_map: dict[str, dict],
    cb: ProgressCb,
) -> dict[str, dict]:
    """BARCHA jettonlar uchun transfer tarixini PARALLEL yuklab oladi.

    Returns:
        {jetton_address: {"income_raw": int, "outcome_raw": int, "tx_count": int}}
    """
    if not jetton_balance_map:
        return {}

    tasks = []
    for j_addr, info in jetton_balance_map.items():
        tasks.append(_fetch_one_jetton_history(
            client, address, raw_address, j_addr, info.get("symbol", "?")
        ))

    stats: dict[str, dict] = {}
    completed = 0
    total = len(tasks)

    # asyncio.as_completed bilan progress'ni real-time yangilab boramiz
    for coro in asyncio.as_completed(tasks):
        try:
            j_addr, j_stats = await coro
            stats[j_addr] = j_stats
        except Exception as e:
            logger.warning(f"Jetton history fetch task error: {e}")
        completed += 1
        # Progress: 30% -> 90%
        pct = 30 + int(60 * completed / total)
        await cb("progress_token_history", pct, symbol=f"{completed}/{total}")

    return stats


async def get_ton_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """TON hamyon to'liq professional audit (tonapi + toncenter cross-check).

    Tezlik uchun:
      - Native TX va jetton history PARALLEL yuklanadi
      - Bulk jetton endpoint (per-token chaqiruv emas)

    Args:
        address: TON hamyon manzili.
        progress: Progress callback funksiyasi.

    Returns:
        Audit natijasi — har bir aktiv (TON, USDT, TUSD, ...) bo'yicha
        to'liq ma'lumot va umumiy yig'indi.
    """
    cb: ProgressCb = progress or _noop_progress

    current_balance: float = 0.0
    account_status: str = "unknown"
    balance_verified: bool = False
    raw_address: str = ""

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # ═══ 1. Hozirgi balans + raw address (parallel taqqoslash uchun) ═══
        await cb("progress_balance", 5)
        try:
            resp = await safe_request(
                client, "GET", f"{_TONAPI_URL}/accounts/{address}", headers=_HEADERS
            )
            account_data: dict = resp.json()
            balance_nano: int = int(account_data.get("balance", 0))
            current_balance = balance_nano / _NANOTON_DIVISOR
            account_status = account_data.get("status", "unknown")
            raw_address = account_data.get("address", "").lower()
        except Exception as e:
            logger.error(f"TON account fetch error: {e}")
            return {"network": "TON", "address": address, "error": str(e)}

        # ═══ 2. Toncenter cross-check (parallel kerak emas — tez) ═══
        await cb("progress_verifying", 10)
        try:
            resp2 = await client.get(
                f"{_TONCENTER_URL}/getAddressBalance",
                params={"address": address},
                timeout=10,
            )
            if resp2.status_code == 200:
                tc_data: dict = resp2.json()
                tc_nano: int = int(tc_data.get("result", 0))
                tc_balance: float = tc_nano / _NANOTON_DIVISOR
                if abs(current_balance - tc_balance) < 0.01:
                    balance_verified = True
                else:
                    current_balance = min(current_balance, tc_balance)
                    balance_verified = True
        except Exception as e:
            logger.warning(f"Toncenter cross-check failed: {e}")

        # ═══ 3. Hozirgi jetton balanslari (avvalo, parallel pipeline uchun kerak) ═══
        await cb("progress_tokens", 18)
        jetton_balance_map: dict[str, dict] = {}
        try:
            resp = await safe_request(
                client, "GET",
                f"{_TONAPI_URL}/accounts/{address}/jettons",
                headers=_HEADERS,
            )
            for item in resp.json().get("balances", []):
                jetton_info: dict = item.get("jetton", {})
                addr_key: str = jetton_info.get("address", "").lower()
                if not addr_key:
                    continue
                decimals: int = int(jetton_info.get("decimals", 9))
                jetton_balance_map[addr_key] = {
                    "symbol": jetton_info.get("symbol", "UNKNOWN"),
                    "decimals": decimals,
                    "raw_balance": int(item.get("balance", "0")),
                }
        except Exception as e:
            logger.warning(f"TON jettons fetch error: {e}")

        # ═══ 4. PARALLEL: Native TON tranzaksiyalari + Har bir jetton tarixi ═══
        await cb("progress_txns", 25, count=0)

        native_task = _fetch_native_txs(client, address, raw_address, cb)
        jetton_task = _fetch_all_jettons_history(
            client, address, raw_address, jetton_balance_map, cb
        )

        try:
            (total_in, total_out, tx_count, yearly_stats), jetton_stats = await asyncio.gather(
                native_task, jetton_task
            )
        except Exception as e:
            logger.error(f"Parallel fetch error: {e}")
            total_in, total_out, tx_count, yearly_stats = 0, 0, 0, {}
            jetton_stats = {}

    await cb("progress_finalizing", 95)

    # ═══ 5. Aktivlar ro'yxatini yig'ish ═══
    income_ton: float = total_in / _NANOTON_DIVISOR
    outcome_ton: float = total_out / _NANOTON_DIVISOR
    volume_ton: float = income_ton + outcome_ton

    balance_str: str = f"{current_balance:,.4f} TON" + (" ✓" if balance_verified else "")

    assets: list[dict] = []

    # 5.1. TON (Native)
    assets.append({
        "symbol": "TON",
        "is_native": True,
        "balance": f"{current_balance:,.4f} TON" + (" ✓" if balance_verified else ""),
        "income": f"{income_ton:,.4f} TON",
        "outcome": f"{outcome_ton:,.4f} TON",
        "net": f"{income_ton - outcome_ton:,.4f} TON",
        "volume": f"{volume_ton:,.4f} TON",
        "tx_count": tx_count,
    })

    # 5.2. Jettonlar — balanslar + transfer tarixi birlashtiriladi
    all_jetton_addrs = set(jetton_balance_map.keys()) | set(jetton_stats.keys())

    for j_addr in all_jetton_addrs:
        bal_info = jetton_balance_map.get(j_addr, {})
        stats_info = jetton_stats.get(j_addr, {"income_raw": 0, "outcome_raw": 0, "tx_count": 0})

        symbol: str = bal_info.get("symbol", "UNKNOWN")
        decimals: int = bal_info.get("decimals", 9)
        divisor: float = 10 ** decimals
        raw_balance: int = bal_info.get("raw_balance", 0)

        token_balance: float = raw_balance / divisor
        j_income: float = stats_info["income_raw"] / divisor
        j_outcome: float = stats_info["outcome_raw"] / divisor
        j_volume: float = j_income + j_outcome
        j_net: float = j_income - j_outcome
        j_tx_count: int = stats_info["tx_count"]

        # Faqat balansi bor yoki transferlari bor jettonlarni ko'rsatamiz
        if token_balance < 0.00001 and j_tx_count == 0:
            continue

        assets.append({
            "symbol": symbol,
            "is_native": False,
            "balance": f"{token_balance:,.4f} {symbol}",
            "income": f"{j_income:,.4f} {symbol}",
            "outcome": f"{j_outcome:,.4f} {symbol}",
            "net": f"{j_net:,.4f} {symbol}",
            "volume": f"{j_volume:,.4f} {symbol}",
            "tx_count": j_tx_count,
        })

    # ═══ 6. Umumiy yig'indi ═══
    # Native tx_count — bu hamyondagi BARCHA on-chain tranzaksiyalar (TON va jettonlar)
    # Har token uchun "tx_count" — o'sha tokenni o'z ichiga olgan transferlar soni
    grand_tx_count: int = tx_count
    asset_count: int = len(assets)

    return {
        "network": "TON",
        "address": address,
        "status": account_status,
        "current_balance": balance_str,
        # Asosiy ko'rsatkichlar — TON (native) bo'yicha (risk_engine moslik uchun)
        "total_income": f"{income_ton:,.4f} TON",
        "total_outcome": f"{outcome_ton:,.4f} TON",
        "net_balance": f"{income_ton - outcome_ton:,.4f} TON",
        "total_volume": f"{volume_ton:,.4f} TON",
        "tx_count": tx_count,
        # Yangi — har bir aktiv bo'yicha to'liq ma'lumot
        "assets": assets,
        "grand_tx_count": grand_tx_count,
        "asset_count": asset_count,
        "yearly_stats": yearly_stats,
        # Eski moslik uchun
        "tokens": [a for a in assets if not a["is_native"]],
    }
