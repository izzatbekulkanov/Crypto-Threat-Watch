"""TON tarmog'i — Professional audit xizmati (tonapi.io + toncenter.com)."""

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


def raw_to_friendly(raw_addr: str, bounceable: bool = False) -> str:
    """TON raw manzilini (0:hex) user-friendly (UQ.../EQ...) formatga o'girish.
    
    Agar allaqachon UQ/EQ bilan boshlangan bo'lsa, o'zgartirishsiz qaytaradi.
    """
    import base64
    import struct

    if not raw_addr:
        return raw_addr

    # Allaqachon user-friendly formatda bo'lsa
    if not raw_addr.startswith("0:") and not raw_addr.startswith("-1:"):
        return raw_addr

    try:
        parts = raw_addr.split(":")
        workchain = int(parts[0])  # 0 yoki -1
        hex_part = parts[1].zfill(64)  # 32 byte
        addr_bytes = bytes.fromhex(hex_part)

        # Tag: bounceable=0x11, non-bounceable=0x51; testnet ga -1 qo'shiladi
        tag = 0x11 if bounceable else 0x51
        wc_byte = workchain & 0xFF

        # 34 bayt: tag + workchain + 32 bayt addr
        data = bytes([tag, wc_byte]) + addr_bytes

        # CRC16-CCITT (XModem)
        crc = 0
        for byte in data:
            crc ^= byte << 8
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
            crc &= 0xFFFF

        full = data + struct.pack(">H", crc)
        return base64.urlsafe_b64encode(full).decode().rstrip("=")
    except Exception:
        return raw_addr  # fallback: o'zgartirmay qaytarish


async def _fetch_native_txs(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    cb: ProgressCb,
) -> list[dict]:
    """TON (native) tranzaksiyalarini yuklab oladi.

    Returns:
        list[dict]: List of transfer dicts.
    """
    transfers: list[dict] = []
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

        page_idx += 1
        # Progress uchun taxminiy hisob
        pct = min(60, 25 + page_idx * 4)
        await cb("progress_txns", pct, count=len(transfers))

        for tx in transactions:
            tx_time = tx.get("utime", 0)
            tx_hash = tx.get("hash", "")

            in_msg: dict | None = tx.get("in_msg")
            if in_msg and in_msg.get("value"):
                src = in_msg.get("source") or {}
                src_addr = src.get("address", "").lower() if isinstance(src, dict) else ""
                if src_addr != raw_address:
                    val = int(in_msg["value"]) / _NANOTON_DIVISOR
                    transfers.append({
                        "tx_hash": tx_hash,
                        "timestamp": tx_time,
                        "symbol": "GRAM",
                        "amount": val,
                        "direction": "in",
                        "counterparty": raw_to_friendly(src_addr)
                    })

            out_msgs: list[dict] = tx.get("out_msgs", [])
            for msg in out_msgs:
                if msg.get("value"):
                    dest = msg.get("destination") or {}
                    dest_addr = dest.get("address", "").lower() if isinstance(dest, dict) else ""
                    if dest_addr != raw_address:
                        val = int(msg["value"]) / _NANOTON_DIVISOR
                        transfers.append({
                            "tx_hash": tx_hash,
                            "timestamp": tx_time,
                            "symbol": "GRAM",
                            "amount": val,
                            "direction": "out",
                            "counterparty": raw_to_friendly(dest_addr)
                        })

        last_lt = transactions[-1].get("lt")
        if not last_lt:
            break
        before_lt = last_lt
        await asyncio.sleep(0.1)

    return transfers


async def _fetch_one_jetton_history(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    jetton_address: str,
    symbol: str,
    decimals: int,
) -> tuple[str, list[dict]]:
    """BIR jetton uchun transfer tarixini yuklab oladi."""
    transfers: list[dict] = []
    divisor: float = 10 ** decimals

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
            event_id = event.get("event_id") or ""
            tx_time = event.get("timestamp", 0)
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
                    transfers.append({
                        "tx_hash": event_id,
                        "timestamp": tx_time,
                        "symbol": symbol,
                        "amount": amt_raw / divisor,
                        "direction": "out",
                        "counterparty": raw_to_friendly(recipient)
                    })
                elif recipient == raw_address:
                    transfers.append({
                        "tx_hash": event_id,
                        "timestamp": tx_time,
                        "symbol": symbol,
                        "amount": amt_raw / divisor,
                        "direction": "in",
                        "counterparty": raw_to_friendly(sender)
                    })

        next_from = data.get("next_from")
        if next_from in (None, 0, "0"):
            last_lt = events[-1].get("lt")
            if not last_lt or last_lt == cursor:
                break
            cursor = last_lt
        else:
            cursor = next_from

        if len(events) < 100:
            break

        await asyncio.sleep(0.1)

    return jetton_address.lower(), transfers


async def _fetch_all_jettons_history(
    client: httpx.AsyncClient,
    address: str,
    raw_address: str,
    jetton_balance_map: dict[str, dict],
    cb: ProgressCb,
) -> list[dict]:
    """BARCHA jettonlar uchun transfer tarixini PARALLEL yuklab oladi.

    Returns:
        list[dict]: List of all jetton transfers.
    """
    if not jetton_balance_map:
        return []

    tasks = []
    for j_addr, info in jetton_balance_map.items():
        tasks.append(_fetch_one_jetton_history(
            client, address, raw_address, j_addr, info.get("symbol", "?"), info.get("decimals", 9)
        ))

    all_transfers: list[dict] = []
    completed = 0
    total = len(tasks)

    for coro in asyncio.as_completed(tasks):
        try:
            _, j_transfers = await coro
            all_transfers.extend(j_transfers)
        except Exception as e:
            logger.warning(f"Jetton history fetch task error: {e}")
        completed += 1
        pct = 30 + int(60 * completed / total)
        await cb("progress_token_history", pct, symbol=f"{completed}/{total}")

    return all_transfers


async def get_ton_balance(
    address: str,
    progress: ProgressCb | None = None,
) -> dict:
    """TON hamyon to'liq professional audit."""
    cb: ProgressCb = progress or _noop_progress

    current_balance: float = 0.0
    account_status: str = "unknown"
    balance_verified: bool = False
    raw_address: str = ""

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        # ═══ 1. Hozirgi balans + raw address ═══
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

        # ═══ 2. Toncenter cross-check ═══
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

        # ═══ 3. Hozirgi jetton balanslari ═══
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

        # Tarixiy 0 balansli jettonlarni aniqlash (har qanday tokenni tahlil qilish uchun)
        try:
            before_lt = None
            for _ in range(3):  # Oxirgi 300 eventni tekshiramiz
                params = {"limit": 100}
                if before_lt:
                    params["before_lt"] = before_lt
                resp_ev = await safe_request(
                    client, "GET",
                    f"{_TONAPI_URL}/accounts/{address}/events",
                    headers=_HEADERS,
                    params=params,
                )
                data_ev = resp_ev.json()
                events = data_ev.get("events", [])
                if not events:
                    break
                for event in events:
                    for action in event.get("actions", []):
                        if action.get("type") == "JettonTransfer":
                            jt = action.get("JettonTransfer", {})
                            j_info = jt.get("jetton", {})
                            j_addr = j_info.get("address", "").lower()
                            if j_addr and j_addr not in jetton_balance_map:
                                decimals = int(j_info.get("decimals", 9))
                                jetton_balance_map[j_addr] = {
                                    "symbol": j_info.get("symbol", "UNKNOWN"),
                                    "decimals": decimals,
                                    "raw_balance": 0,
                                }
                last_lt = events[-1].get("lt")
                if not last_lt:
                    break
                before_lt = last_lt
                if len(events) < 100:
                    break
        except Exception as e:
            logger.warning(f"Error discovering jettons from events: {e}")

        # ═══ 4. PARALLEL: Native TON tranzaksiyalari + Jettonlar tarixi ═══
        await cb("progress_txns", 25, count=0)

        native_task = _fetch_native_txs(client, address, raw_address, cb)
        jetton_task = _fetch_all_jettons_history(
            client, address, raw_address, jetton_balance_map, cb
        )

        try:
            native_transfers, jetton_transfers = await asyncio.gather(
                native_task, jetton_task
            )
        except Exception as e:
            logger.error(f"Parallel fetch error: {e}")
            native_transfers, jetton_transfers = [], []

    # ═══ 5. Swaplarni aniqlash va ajratish ═══
    all_transfers = native_transfers + jetton_transfers
    from utils import process_transfers_and_detect_swaps
    normal_transfers, swaps = process_transfers_and_detect_swaps(all_transfers)

    # ═══ 6. Aktivlar statistikasini hisoblash ═══
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

    # Yillik statistika (faqat normal native GRAM uchun)
    yearly_stats: dict[str, dict[str, float]] = {}
    for t in normal_transfers:
        if t["symbol"] == "GRAM":
            year = "Unknown"
            if t["timestamp"]:
                year = str(datetime.fromtimestamp(t["timestamp"], tz=timezone.utc).year)
            if year not in yearly_stats:
                yearly_stats[year] = {"in": 0.0, "out": 0.0}
            if t["direction"] == "in":
                yearly_stats[year]["in"] += t["amount"]
            else:
                yearly_stats[year]["out"] += t["amount"]

    # GRAM (Native) statistikalari
    gram_stats = token_stats.get("GRAM", {"income": 0.0, "outcome": 0.0, "tx_count": 0})
    income_gram = gram_stats["income"]
    outcome_gram = gram_stats["outcome"]
    volume_gram = income_gram + outcome_gram

    balance_str = f"{current_balance:,.4f} GRAM" + (" ✓" if balance_verified else "")

    assets: list[dict] = []
    assets.append({
        "symbol": "GRAM",
        "is_native": True,
        "balance": balance_str,
        "income": f"{income_gram:,.4f} GRAM",
        "outcome": f"{outcome_gram:,.4f} GRAM",
        "net": f"{income_gram - outcome_gram:,.4f} GRAM",
        "volume": f"{volume_gram:,.4f} GRAM",
        "tx_count": gram_stats["tx_count"],
    })

    # Jettonlar statistikalari
    for j_addr, bal_info in jetton_balance_map.items():
        symbol = bal_info["symbol"]
        decimals = bal_info["decimals"]
        raw_balance = bal_info["raw_balance"]
        token_balance = raw_balance / (10 ** decimals)

        j_stats = token_stats.get(symbol, {"income": 0.0, "outcome": 0.0, "tx_count": 0})
        j_income = j_stats["income"]
        j_outcome = j_stats["outcome"]
        j_volume = j_income + j_outcome
        j_net = j_income - j_outcome
        j_tx_count = j_stats["tx_count"]

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

    grand_tx_count = len(normal_transfers)
    asset_count = len(assets)

    return {
        "network": "TON",
        "address": address,
        "status": account_status,
        "current_balance": balance_str,
        "total_income": f"{income_gram:,.4f} GRAM",
        "total_outcome": f"{outcome_gram:,.4f} GRAM",
        "net_balance": f"{income_gram - outcome_gram:,.4f} GRAM",
        "total_volume": f"{volume_gram:,.4f} GRAM",
        "tx_count": grand_tx_count,
        "assets": assets,
        "grand_tx_count": grand_tx_count,
        "asset_count": asset_count,
        "yearly_stats": yearly_stats,
        "swaps": swaps,
        "normal_transfers": normal_transfers,
        "tokens": [a for a in assets if not a["is_native"]],
    }
