"""Crypto Threat Watch — Professional Multi-Chain Audit Telegram Bot."""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    BotCommand,
    WebAppInfo,
)

from config import BOT_TOKEN, ADMIN_PASSWORD, RATE_LIMIT_PER_MINUTE, WEBAPP_URL
from utils import parse_crypto_link
from database import (
    init_db,
    register_user,
    get_user,
    set_language,
    increment_query_count,
    check_rate_limit,
    set_admin,
    is_admin,
    get_all_users,
    get_stats,
    log_audit,
    get_recent_audits,
    get_user_audits,
)
from texts import t
from risk_engine import assess_risk
from services.ton_api import get_ton_balance
from services.eth_api import get_eth_balance
from services.tron_api import get_tron_usdt_balance

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger: logging.Logger = logging.getLogger(__name__)

# Bot va Dispatcher
storage: MemoryStorage = MemoryStorage()
bot: Bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
)
dp: Dispatcher = Dispatcher(storage=storage)


# ═══════════════════════════════════════════
# FSM States
# ═══════════════════════════════════════════
class Registration(StatesGroup):
    """Ro'yxatdan o'tish holatlari."""
    choosing_language = State()
    waiting_for_alias = State()


class AdminAuth(StatesGroup):
    """Admin autentifikatsiya."""
    waiting_for_password = State()


# ═══════════════════════════════════════════
# Klaviaturalar
# ═══════════════════════════════════════════
def language_keyboard() -> InlineKeyboardMarkup:
    """Til tanlash tugmalari."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz"),
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
        ]
    ])


# ═══════════════════════════════════════════
# /start
# ═══════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    """/start — til tanlash va ro'yxatdan o'tish."""
    await state.clear()
    user = get_user(message.from_user.id)

    if user:
        lang: str = user["language"]
        await message.answer(t("help", lang), parse_mode=ParseMode.MARKDOWN)
        return

    await state.set_state(Registration.choosing_language)
    await message.answer(
        "🛡 *Crypto Threat Watch*\n\n" + t("choose_language", "uz"),
        reply_markup=language_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ═══════════════════════════════════════════
# Til tanlash
# ═══════════════════════════════════════════
@dp.callback_query(F.data.startswith("lang_"))
async def on_language_select(callback: CallbackQuery, state: FSMContext) -> None:
    """Til tanlash callback."""
    lang: str = callback.data.replace("lang_", "")
    await state.update_data(language=lang)

    user = get_user(callback.from_user.id)
    if user:
        # Mavjud foydalanuvchi tilni o'zgartirmoqda
        set_language(callback.from_user.id, lang)
        await callback.message.edit_text(
            t("language_changed", lang), parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer()
        return

    # Yangi foydalanuvchi — taxallus so'rash
    await state.set_state(Registration.waiting_for_alias)
    await callback.message.edit_text(
        t("ask_alias", lang), parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


# ═══════════════════════════════════════════
# Taxallus qabul qilish
# ═══════════════════════════════════════════
@dp.message(Registration.waiting_for_alias)
async def on_alias_received(message: types.Message, state: FSMContext) -> None:
    """Taxallusni qabul qilish va ro'yxatdan o'tkazish."""
    data = await state.get_data()
    lang: str = data.get("language", "uz")
    alias: str = (message.text or "").strip()

    if len(alias) < 3:
        await message.answer(t("alias_too_short", lang), parse_mode=ParseMode.MARKDOWN)
        return

    register_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        alias=alias,
        language=lang,
    )
    await state.clear()
    await message.answer(
        t("registered_success", lang, alias=alias),
        parse_mode=ParseMode.MARKDOWN,
    )


# ═══════════════════════════════════════════
# /help
# ═══════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """Yordam."""
    user = get_user(message.from_user.id)
    lang: str = user["language"] if user else "uz"
    await message.answer(t("help", lang), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /language
# ═══════════════════════════════════════════
@dp.message(Command("language"))
async def cmd_language(message: types.Message) -> None:
    """Tilni o'zgartirish."""
    user = get_user(message.from_user.id)
    lang: str = user["language"] if user else "uz"
    await message.answer(
        t("choose_language", lang),
        reply_markup=language_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )


# ═══════════════════════════════════════════
# /mystats
# ═══════════════════════════════════════════
@dp.message(Command("mystats"))
async def cmd_mystats(message: types.Message) -> None:
    """Shaxsiy statistika."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    registered: str = user.get("registered_at", "—")
    if registered and len(registered) > 10:
        registered = registered[:10]

    await message.answer(
        t("my_stats", lang, alias=user["alias"], count=user["query_count"], registered=registered),
        parse_mode=ParseMode.MARKDOWN,
    )


# ═══════════════════════════════════════════
# /history
# ═══════════════════════════════════════════
@dp.message(Command("history"))
async def cmd_history(message: types.Message) -> None:
    """So'rovlar tarixi."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    audits = get_user_audits(message.from_user.id)

    if not audits:
        await message.answer(t("history_empty", lang), parse_mode=ParseMode.MARKDOWN)
        return

    text: str = t("history_header", lang)
    for i, audit in enumerate(audits, 1):
        date_str: str = audit.get("created_at", "")[:16]
        text += (
            f"{i}. `{audit['network']}` | "
            f"`{audit['address'][:10]}...`\n"
            f"   {audit['risk_level']} | {date_str}\n\n"
        )

    await message.answer(text, parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /admin
# ═══════════════════════════════════════════
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext) -> None:
    """Admin autentifikatsiya."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]

    if is_admin(message.from_user.id):
        await message.answer(t("admin_success", lang), parse_mode=ParseMode.MARKDOWN)
        return

    await state.set_state(AdminAuth.waiting_for_password)
    await message.answer(t("admin_prompt", lang), parse_mode=ParseMode.MARKDOWN)


@dp.message(AdminAuth.waiting_for_password)
async def on_admin_password(message: types.Message, state: FSMContext) -> None:
    """Admin parolini tekshirish."""
    user = get_user(message.from_user.id)
    lang: str = user["language"] if user else "uz"

    if message.text and message.text.strip() == ADMIN_PASSWORD:
        set_admin(message.from_user.id)
        await state.clear()
        await message.answer(t("admin_success", lang), parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Yangi admin: {message.from_user.id}")
    else:
        await state.clear()
        await message.answer(t("admin_fail", lang), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /stats (admin)
# ═══════════════════════════════════════════
@dp.message(Command("stats"))
async def cmd_stats(message: types.Message) -> None:
    """Umumiy statistika (admin)."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    if not is_admin(message.from_user.id):
        await message.answer(t("not_admin", lang), parse_mode=ParseMode.MARKDOWN)
        return

    stats = get_stats()
    await message.answer(
        t("global_stats", lang,
          users=stats["total_users"],
          queries=stats["total_queries"],
          audits=stats["total_audits"]),
        parse_mode=ParseMode.MARKDOWN,
    )


# ═══════════════════════════════════════════
# /users (admin)
# ═══════════════════════════════════════════
@dp.message(Command("users"))
async def cmd_users(message: types.Message) -> None:
    """Foydalanuvchilar ro'yxati (admin)."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    if not is_admin(message.from_user.id):
        await message.answer(t("not_admin", lang), parse_mode=ParseMode.MARKDOWN)
        return

    users = get_all_users()
    if not users:
        await message.answer("📭 Foydalanuvchilar yo'q.")
        return

    lines: list[str] = ["👥 *Foydalanuvchilar:*\n━━━━━━━━━━━━━━━━━━━━━\n"]
    for i, u in enumerate(users, 1):
        badge: str = " 👑" if u["is_admin"] else ""
        lines.append(
            f"{i}. `{u['alias']}`{badge} — *{u['query_count']}* so'rov"
        )

    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /audits (admin)
# ═══════════════════════════════════════════
@dp.message(Command("audits"))
async def cmd_audits(message: types.Message) -> None:
    """Oxirgi auditlar (admin)."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    if not is_admin(message.from_user.id):
        await message.answer(t("not_admin", lang), parse_mode=ParseMode.MARKDOWN)
        return

    audits = get_recent_audits(15)
    if not audits:
        await message.answer("📭 Auditlar yo'q.")
        return

    lines: list[str] = ["📋 *Oxirgi auditlar:*\n━━━━━━━━━━━━━━━━━━━━━\n"]
    for i, a in enumerate(audits, 1):
        date_str: str = a.get("created_at", "")[:16]
        lines.append(
            f"{i}. 👤`{a['alias']}` | `{a['network']}`\n"
            f"   `{a['address'][:12]}...` | {a['risk_level']}\n"
            f"   📅 {date_str}\n"
        )

    await message.answer("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ═══════════════════════════════════════════
# /web (admin) — Telegram Mini App (GitHub Pages)
# ═══════════════════════════════════════════
@dp.message(Command("web"))
async def cmd_web(message: types.Message) -> None:
    """Admin panel — Telegram Mini App ochish (GitHub Pages)."""
    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]
    if not is_admin(message.from_user.id):
        await message.answer(t("not_admin", lang), parse_mode=ParseMode.MARKDOWN)
        return

    if not WEBAPP_URL:
        await message.answer(
            "❌ *Web panel sozlanmagan.*\n\n"
            "`.env` faylga `WEBAPP_URL` qo'shing.\n"
            "Masalan: `https://username.github.io/Crypto-Threat-Watch/`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Ma'lumotlarni yig'ish va URL hash ga qo'shish
    import json
    import base64
    import time
    from urllib.parse import quote

    stats = get_stats()
    users = get_all_users()
    audits = get_recent_audits(20)

    # Ma'lumotlarni minimal qilish (faqat kerakli fieldlar)
    compact_users = []
    for u in users:
        compact_users.append({
            "id": u.get("user_id"),
            "a": u.get("alias", ""),
            "u": u.get("username", ""),
            "q": u.get("query_count", 0),
            "d": (u.get("registered_at", "") or "")[:10],
            "ad": u.get("is_admin", 0),
        })

    compact_audits = []
    for a in audits:
        compact_audits.append({
            "n": a.get("network", ""),
            "addr": a.get("address", ""),
            "r": a.get("risk_level", "LOW"),
            "al": a.get("alias", ""),
            "t": (a.get("created_at", "") or "")[:16],
        })

    data = {
        "s": stats,
        "u": compact_users,
        "a": compact_audits,
    }

    def _encode(d: dict) -> str:
        """Dict -> URL-safe base64 (UTF-8, padding yo'q)."""
        json_bytes = json.dumps(d, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        return base64.urlsafe_b64encode(json_bytes).decode().rstrip('=')

    # GitHub Pages URL + data (query param orqali, hash emas — Telegram hash'ni o'chiradi)
    base_url: str = WEBAPP_URL.rstrip("/") + "/index.html"
    data_b64: str = _encode(data)
    cache_buster = int(time.time())
    webapp_url: str = f"{base_url}?d={data_b64}&v={cache_buster}"

    # Telegram URL limit tekshiruvi (~2048)
    if len(webapp_url) > 2048:
        data["a"] = compact_audits[:10]
        data_b64 = _encode(data)
        webapp_url = f"{base_url}?d={data_b64}&v={cache_buster}"

    if len(webapp_url) > 2048:
        data = {"s": stats, "u": compact_users[:5], "a": compact_audits[:5]}
        data_b64 = _encode(data)
        webapp_url = f"{base_url}?d={data_b64}&v={cache_buster}"

    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(
            text="🖥 Admin Panel ochish",
            web_app=WebAppInfo(url=webapp_url),
        )]
    ], resize_keyboard=True)

    await message.answer(
        "🌐 *Crypto Threat Watch — Admin Panel*\n\n"
        "Quyidagi tugma orqali kengaytirilgan web boshqaruv paneliga kiring.\n"
        "_Ushbu panel orqali foydalanuvchilar va auditlarni boshqarish mumkin._",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )


# ═══════════════════════════════════════════
# Asosiy havola handler
# ═══════════════════════════════════════════
@dp.message()
async def handle_link(message: types.Message, state: FSMContext) -> None:
    """Blokcheyn havolasini tahlil qilish — asosiy funksiya."""
    text: str | None = message.text
    if not text:
        return

    user = get_user(message.from_user.id)
    if not user:
        await message.answer(t("not_registered", "uz"), parse_mode=ParseMode.MARKDOWN)
        return

    lang: str = user["language"]

    # Havolani tahlil qilish
    result = parse_crypto_link(text.strip())
    if result is None:
        await message.answer(t("invalid_link", lang), parse_mode=ParseMode.MARKDOWN)
        return

    network: str = result[0]
    address: str = result[1]

    # Rate limit tekshiruvi
    if not check_rate_limit(message.from_user.id, RATE_LIMIT_PER_MINUTE):
        await message.answer(t("rate_limited", lang), parse_mode=ParseMode.MARKDOWN)
        return

    short_addr: str = f"{address[:8]}...{address[-6:]}"

    # Vizual status
    status_msg: types.Message = await message.answer(
        t("analyzing", lang, network=network, short_addr=short_addr),
        parse_mode=ParseMode.MARKDOWN,
    )

    try:
        # API chaqirish
        if network == "TON":
            data: dict = await get_ton_balance(address)
        elif network == "ETH":
            data = await get_eth_balance(address)
        elif network == "TRON":
            data = await get_tron_usdt_balance(address)
        else:
            await status_msg.edit_text("❌ Unknown network.")
            return

        # API xatolik tekshiruvi
        if "error" in data:
            await status_msg.edit_text(
                t("api_error", lang, error=data["error"]),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        # So'rov hisobini oshirish
        increment_query_count(message.from_user.id)

        # Risk baholash
        risk_level, risk_emoji = assess_risk(data)

        # ═══ HISOBOT FORMATLASH ═══
        report: str = t(
            "result_header", lang,
            network=data["network"],
            address=data["address"],
        )

        # Hozirgi balans
        report += t("result_balance", lang, current_balance=data.get("current_balance", "—"))

        # Tranzaksiya xulosasi
        report += t(
            "result_summary", lang,
            income=data["total_income"],
            outcome=data["total_outcome"],
            net=data["net_balance"],
            volume=data.get("total_volume", "—"),
            tx_count=data.get("tx_count", 0),
        )

        # Risk darajasi
        report += t("result_risk", lang, risk_emoji=risk_emoji, risk_level=risk_level)

        # Tokenlar guruhi
        tokens: list[dict] = data.get("tokens", [])
        if tokens:
            report += t("result_tokens_header", lang)
            for tk in tokens:
                symbol: str = tk.get("symbol", "?")
                current: str = tk.get("balance", "") or tk.get("current_balance", "")
                income: str = tk.get("income", "")
                outcome: str = tk.get("outcome", "")
                volume: str = tk.get("volume", "")

                report += f"• *{symbol}*"
                if current and current not in ("—", "0.0000"):
                    report += f": 💎 `{current}`"
                report += "\n"
                if income or outcome:
                    report += f"  📥 `{income}` | 📤 `{outcome}` | 🔄 `{volume}`\n"

        # Footer
        now: str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report += t("result_footer", lang, timestamp=now)

        # Audit logga saqlash
        summary: str = f"In:{data['total_income']} Out:{data['total_outcome']}"
        log_audit(message.from_user.id, network, address, summary, risk_level)

        # Web App URL tayyorlash
        keyboard = None
        if WEBAPP_URL:
            import json
            import base64
            import time
            webapp_data = {
                "n": data.get("network", ""),
                "addr": data.get("address", ""),
                "bal": data.get("current_balance", ""),
                "in": data.get("total_income", ""),
                "out": data.get("total_outcome", ""),
                "net": data.get("net_balance", ""),
                "vol": data.get("total_volume", ""),
                "tx": data.get("tx_count", 0),
                "r": risk_level,
                "y": data.get("yearly_stats", {}),
                "tk": [{"s": tk.get("symbol", ""), "b": tk.get("balance", ""), "c": tk.get("current_balance", "")} for tk in data.get("tokens", [])[:15]]
            }
            json_bytes = json.dumps(webapp_data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            data_b64 = base64.urlsafe_b64encode(json_bytes).decode().rstrip('=')
            cache_buster = int(time.time())
            base_url = WEBAPP_URL.rstrip("/") + "/report.html"
            webapp_url = f"{base_url}?d={data_b64}&v={cache_buster}"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=t("view_in_webapp", lang),
                    web_app=WebAppInfo(url=webapp_url)
                )]
            ])

        # Xabar uzunligi nazorati (Telegram limit: 4096)
        if len(report) > 4000:
            # Ikki qismga bo'lish
            mid: int = len(report) // 2
            split_pos: int = report.rfind("\n", 0, mid)
            if split_pos == -1:
                split_pos = mid

            await status_msg.edit_text(report[:split_pos], parse_mode=ParseMode.MARKDOWN)
            await message.answer(report[split_pos:], parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        else:
            await status_msg.edit_text(report, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Audit xatolik [{network}:{address[:10]}]: {e}", exc_info=True)
        error_msg: str = str(e)[:100] if str(e) else "Unknown error"
        await status_msg.edit_text(
            t("api_error", lang, error=error_msg),
            parse_mode=ParseMode.MARKDOWN,
        )


# ═══════════════════════════════════════════
# WebApp orqali boshqaruv (sendData)
# ═══════════════════════════════════════════
@dp.message(F.web_app_data)
async def handle_webapp_data(message: types.Message) -> None:
    """WebApp dan kelgan ma'lumotlarni qabul qilish (Admin boshqaruvi)."""
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer("⛔ Sizda yetarli huquqlar yo'q.")
        return

    try:
        import json
        from database import toggle_admin, update_alias
        data_str = message.web_app_data.data
        payload = json.loads(data_str)
        
        action = payload.get("action")
        target_user = payload.get("user_id")
        
        if action == "toggle_admin":
            new_status = toggle_admin(target_user)
            status_text = "Admin qilingan" if new_status else "Adminlikdan olingan"
            await message.answer(f"✅ Foydalanuvchi ({target_user}) {status_text}.")
        elif action == "edit_alias":
            new_alias = payload.get("alias")
            if new_alias:
                update_alias(target_user, new_alias)
                await message.answer(f"✅ Foydalanuvchi ({target_user}) taxallusi `{new_alias}` ga o'zgartirildi.", parse_mode=ParseMode.MARKDOWN)
                
    except Exception as e:
        logger.error(f"WebApp ma'lumotlarni qabul qilishda xatolik: {e}")
        await message.answer(f"❌ Xatolik: {e}")

# ═══════════════════════════════════════════
# Bot buyruqlarini sozlash
# ═══════════════════════════════════════════
async def set_bot_commands() -> None:
    """Bot buyruqlar menyusini sozlash."""
    commands: list[BotCommand] = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="language", description="Tilni o'zgartirish"),
        BotCommand(command="mystats", description="Shaxsiy statistika"),
        BotCommand(command="history", description="So'rovlar tarixi"),
        BotCommand(command="admin", description="Admin panel"),
        BotCommand(command="web", description="Web panel (admin)"),
    ]
    await bot.set_my_commands(commands)


# ═══════════════════════════════════════════
# Main
# ═══════════════════════════════════════════
async def main() -> None:
    """Botni ishga tushirish."""
    init_db()
    await set_bot_commands()

    logger.info("🛡 Crypto Threat Watch Bot ishga tushdi!")
    logger.info(f"Rate limit: {RATE_LIMIT_PER_MINUTE} so'rov/daqiqa")
    if WEBAPP_URL:
        logger.info(f"🌐 Web App: {WEBAPP_URL}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
