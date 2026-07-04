"""Crypto Threat Watch — Professional Multi-Chain Audit Telegram Bot."""

import asyncio
import logging
import time
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, types, F, BaseMiddleware
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
    approve_user,
    is_approved,
    get_admin_ids,
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
# Middleware
# ═══════════════════════════════════════════
from aiogram.types import TelegramObject

class AccessMiddleware(BaseMiddleware):
    """Foydalanuvchining botdan foydalanish huquqini tekshiruvchi middleware."""
    async def __call__(
        self,
        handler,
        event: TelegramObject,
        data: dict,
    ):
        user_id = None
        message = None
        is_callback = False

        if isinstance(event, types.Message):
            user_id = event.from_user.id
            message = event
        elif isinstance(event, types.CallbackQuery):
            user_id = event.from_user.id
            message = event.message
            is_callback = True
        else:
            return await handler(event, data)

        # FSM holatini tekshirish
        state: FSMContext = data.get("state")
        current_state = await state.get_state() if state else None

        # Agar ro'yxatdan o'tish jarayonida bo'lsa, o'tkazib yuboramiz
        if current_state in (Registration.choosing_language, Registration.waiting_for_alias):
            return await handler(event, data)

        # Admin parolini kiritayotgan bo'lsa, o'tkazib yuboramiz
        if current_state == AdminAuth.waiting_for_password:
            return await handler(event, data)

        # Start va Admin komandalari har doim ochiq bo'lishi kerak
        if isinstance(event, types.Message) and event.text:
            text = event.text.strip()
            if text.startswith("/start") or text.startswith("/admin"):
                return await handler(event, data)

        # Ruxsatlarni tekshirish
        user = get_user(user_id)
        if not user:
            # Agar foydalanuvchi bazada bo'lmasa, /start ga yo'naltiramiz
            if not is_callback and message:
                await message.answer(
                    "🛡 *Crypto Threat Watch*\n\nBotdan foydalanish uchun ro'yxatdan o'tish zarur. Iltimos, /start buyrug'ini bosing.",
                    parse_mode=ParseMode.MARKDOWN
                )
            return

        # Ruxsat tekshiruvi: admin bo'lsa yoki tasdiqlangan bo'lsa
        if user["is_admin"] or is_approved(user_id):
            return await handler(event, data)

        # Ruxsat berilmagan bo'lsa
        lang = user.get("language", "uz")
        if is_callback:
            await event.answer(t("access_denied", lang), show_alert=True)
        else:
            await message.answer(t("access_denied", lang), parse_mode=ParseMode.MARKDOWN)
        return

# Middleware-ni ro'yxatdan o'tkazish
dp.message.outer_middleware(AccessMiddleware())
dp.callback_query.outer_middleware(AccessMiddleware())


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
# Progress bar yaratish
# ═══════════════════════════════════════════
def _build_progress_bar(percent: int, width: int = 12) -> str:
    """Yashil/oq progress bar qatorini qaytaradi.

    Args:
        percent: 0-100 oraliqdagi qiymat.
        width: Bar uzunligi (belgilarda).

    Returns:
        "▓▓▓▓░░░░░░░░ 33%" ko'rinishidagi qator.
    """
    percent = max(0, min(100, percent))
    filled: int = int(width * percent / 100)
    bar: str = "▓" * filled + "░" * (width - filled)
    return f"`{bar}` *{percent}%*"


def make_progress_callback(
    status_msg: types.Message,
    network: str,
    short_addr: str,
    lang: str,
):
    """Telegram xabarini progress bilan yangilab boradigan callback yaratadi.

    Telegram rate-limit (~1 xabar/sek) ni hurmat qilib, xabar 1.5 soniyada
    bir martadan tez-tez yangilanmaydi. Shuningdek, percent o'zgarmaganda
    behuda yangilanish bo'lmaydi.
    """
    state: dict = {
        "last_update": 0.0,
        "last_pct": -1,
        "last_text": "",
        "lock": asyncio.Lock(),
    }

    async def _cb(step_key: str, percent: int, **extra) -> None:
        # Throttle: 1.5 soniya — Telegram rate-limit oldini olish
        now: float = time.monotonic()
        if percent < 100 and percent != 98:
            if now - state["last_update"] < 1.5:
                return
            if percent == state["last_pct"]:
                return

        async with state["lock"]:
            try:
                step_text: str = t(step_key, lang, **extra)
                bar: str = _build_progress_bar(percent)
                new_text: str = t(
                    "analyzing", lang,
                    network=network,
                    short_addr=short_addr,
                    bar=bar,
                    step=step_text,
                )

                # Bir xil xabar bo'lsa, yangilamaymiz (Telegram xato bermasligi uchun)
                if new_text == state["last_text"]:
                    return

                await status_msg.edit_text(
                    new_text, parse_mode=ParseMode.MARKDOWN
                )
                state["last_update"] = now
                state["last_pct"] = percent
                state["last_text"] = new_text
            except Exception as e:
                # Telegram xatoliklarni jim yutamiz (rate limit, message not modified)
                logger.debug(f"Progress update skipped: {e}")

    return _cb


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
    """Taxallusni qabul qilish, ro'yxatdan o'tkazish va admin tasdig'iga yuborish."""
    data = await state.get_data()
    lang: str = data.get("language", "uz")
    alias: str = (message.text or "").strip()

    if len(alias) < 3:
        await message.answer(t("alias_too_short", lang), parse_mode=ParseMode.MARKDOWN)
        return

    user_id = message.from_user.id
    username = message.from_user.username or "noname"

    register_user(
        user_id=user_id,
        username=username,
        alias=alias,
        language=lang,
    )
    await state.clear()
    
    # Kutilayotgani haqida xabar berish
    await message.answer(
        t("request_pending", lang),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Adminlarga xabar yuborish
    admin_ids = get_admin_ids()
    if not admin_ids:
        logger.warning("Bazada birorta ham admin topilmadi! Birinchi bo'lib /admin orqali tizimga kiring.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_req:{user_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_req:{user_id}"),
        ]
    ])

    admin_msg_text = t("admin_approval_request", "uz", alias=alias, user_id=user_id, username=username)
    for admin_id in admin_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=admin_msg_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.warning(f"Admin {admin_id} ga xabar yuborib bo'lmadi: {e}")


# ═══════════════════════════════════════════
# Admin tasdiqlash arizalari uchun callback handlers
# ═══════════════════════════════════════════
@dp.callback_query(F.data.startswith("approve_req:"))
async def on_approve_request(callback: CallbackQuery) -> None:
    """Admin foydalanuvchi arizasini tasdiqlaganida."""
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("⛔ Sizda yetarli huquqlar yo'q.", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[1])
    target_user = get_user(target_user_id)
    if not target_user:
        await callback.answer("❌ Foydalanuvchi topilmadi.", show_alert=True)
        return

    approve_user(target_user_id, True)

    admin_user = get_user(user_id)
    admin_alias = admin_user["alias"] if admin_user else "Admin"

    alias = target_user["alias"]
    lang: str = target_user["language"] or "uz"
    
    await callback.answer(f"✅ {alias} tasdiqlandi.")
    
    new_text = t("admin_approved_log", lang, alias=alias, user_id=target_user_id, admin=admin_alias)
    await callback.message.edit_text(new_text, reply_markup=None)

    # Foydalanuvchini xabardor qilish
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=t("user_approved_notification", lang),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Foydalanuvchi {target_user_id} ga tasdiqlash xabari yuborib bo'lmadi: {e}")


@dp.callback_query(F.data.startswith("reject_req:"))
async def on_reject_request(callback: CallbackQuery) -> None:
    """Admin foydalanuvchi arizasini rad etganida."""
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("⛔ Sizda yetarli huquqlar yo'q.", show_alert=True)
        return

    target_user_id = int(callback.data.split(":")[1])
    target_user = get_user(target_user_id)
    if not target_user:
        await callback.answer("❌ Foydalanuvchi topilmadi.", show_alert=True)
        return

    approve_user(target_user_id, False)

    admin_user = get_user(user_id)
    admin_alias = admin_user["alias"] if admin_user else "Admin"

    alias = target_user["alias"]
    lang: str = target_user["language"] or "uz"
    
    await callback.answer(f"❌ {alias} arizasi rad etildi.")
    
    new_text = t("admin_rejected_log", lang, alias=alias, user_id=target_user_id, admin=admin_alias)
    await callback.message.edit_text(new_text, reply_markup=None)

    # Foydalanuvchini xabardor qilish
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=t("user_rejected_notification", lang),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.warning(f"Foydalanuvchi {target_user_id} ga rad etish xabari yuborib bo'lmadi: {e}")


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
# /risk — Risk darajasi haqida ma'lumot
# ═══════════════════════════════════════════
@dp.message(Command("risk"))
async def cmd_risk(message: types.Message) -> None:
    """Risk darajasi qanday hisoblanishi haqida batafsil ma'lumot."""
    user = get_user(message.from_user.id)
    lang: str = user["language"] if user else "uz"
    await message.answer(t("risk_info", lang), parse_mode=ParseMode.MARKDOWN)


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
            "ap": u.get("is_approved", 0),
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
    import web_server
    api_url = getattr(web_server, "_tunnel_url", "")

    base_url: str = WEBAPP_URL.rstrip("/") + "/index.html"
    data_b64: str = _encode(data)
    cache_buster = int(time.time())
    
    api_param = f"&api={api_url}" if api_url else ""
    webapp_url: str = f"{base_url}?d={data_b64}&v={cache_buster}{api_param}"

    # Telegram URL limit tekshiruvi (~2048)
    if len(webapp_url) > 2048:
        data["a"] = compact_audits[:10]
        data_b64 = _encode(data)
        webapp_url = f"{base_url}?d={data_b64}&v={cache_buster}{api_param}"

    if len(webapp_url) > 2048:
        data = {"s": stats, "u": compact_users[:5], "a": compact_audits[:5]}
        data_b64 = _encode(data)
        webapp_url = f"{base_url}?d={data_b64}&v={cache_buster}{api_param}"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🖥 Admin Panel ochish",
            web_app=WebAppInfo(url=webapp_url),
        )]
    ])

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

    # Vizual status — boshlang'ich progress bar bilan
    initial_bar: str = _build_progress_bar(0)
    status_msg: types.Message = await message.answer(
        t("analyzing", lang,
          network=network,
          short_addr=short_addr,
          bar=initial_bar,
          step=t("progress_init", lang)),
        parse_mode=ParseMode.MARKDOWN,
    )

    # Progress callback — har bir API bosqichida xabarni yangilaydi
    progress_cb = make_progress_callback(status_msg, network, short_addr, lang)

    try:
        # API chaqirish
        if network == "TON":
            data: dict = await get_ton_balance(address, progress=progress_cb)
        elif network == "ETH":
            data = await get_eth_balance(address, progress=progress_cb)
        elif network == "TRON":
            data = await get_tron_usdt_balance(address, progress=progress_cb)
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

        # Risk darajasi (yuqorida — eng muhim ma'lumot)
        report += t("result_risk", lang, risk_emoji=risk_emoji, risk_level=risk_level)

        # Har bir aktiv bo'yicha alohida blok (TON, USDT, TUSD, ...)
        assets: list[dict] = data.get("assets", [])
        if assets:
            report += t("assets_header", lang)
            for asset in assets:
                report += t(
                    "asset_block", lang,
                    symbol=asset.get("symbol", "?"),
                    balance=asset.get("balance", "—"),
                    income=asset.get("income", "—"),
                    outcome=asset.get("outcome", "—"),
                    net=asset.get("net", "—"),
                    volume=asset.get("volume", "—"),
                    tx_count=asset.get("tx_count", 0),
                )

            # Yakuniy umumiy yig'indi
            report += t(
                "grand_total", lang,
                asset_count=data.get("asset_count", len(assets)),
                tx_count=data.get("grand_tx_count", data.get("tx_count", 0)),
            )
        else:
            # Eski format (ETH/TRON hali yangi formatga o'tmagan bo'lsa)
            report += t(
                "result_summary", lang,
                income=data["total_income"],
                outcome=data["total_outcome"],
                net=data["net_balance"],
                volume=data.get("total_volume", "—"),
                tx_count=data.get("tx_count", 0),
            )

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

        # Swaps qo'shish
        swaps = data.get("swaps", [])
        if swaps:
            swap_title = {
                "uz": "\n🔄 *Ichki almashtirishlar (Swaps):*\n",
                "ru": "\n🔄 *Внутренние обмены (Swaps):*\n",
                "en": "\n🔄 *Internal Swaps:*\n",
            }.get(lang, "\n🔄 *Internal Swaps:*\n")
            report += swap_title
            for swap in swaps[:5]:
                dt_str = "—"
                ts = swap.get("timestamp")
                if ts:
                    try:
                        dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%m-%d %H:%M")
                    except Exception:
                        dt_str = str(ts)
                report += f"• `{dt_str}` | {swap['from_desc']} ➡️ {swap['to_desc']}\n"
            if len(swaps) > 5:
                more_text = {
                    "uz": f"• _...yana {len(swaps) - 5} ta operatsiya (batafsil hisobot faylida)._\n",
                    "ru": f"• _...еще {len(swaps) - 5} операций (подробнее в файле отчета)._\n",
                    "en": f"• _...and {len(swaps) - 5} more operations (details in the report file)._\n",
                }.get(lang, f"• _...and {len(swaps) - 5} more (details in report)._\n")
                report += more_text

        # Footer
        now: str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        report += t("result_footer", lang, timestamp=now)

        # Audit logga saqlash
        summary: str = f"In:{data['total_income']} Out:{data['total_outcome']}"
        log_audit(message.from_user.id, network, address, summary, risk_level)

        # Word hisoboti yaratish
        from services.report_generator import generate_docx_report
        from aiogram.types import FSInputFile
        import os

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_addr = address[:8]
        file_name = f"Audit_{network}_{safe_addr}_{timestamp_str}.docx"
        reports_dir = "/home/superadmin/kiberhavfsizlik/Crypto-Threat-Watch/reports"
        os.makedirs(reports_dir, exist_ok=True)
        file_path = os.path.join(reports_dir, file_name)

        doc_file = None
        try:
            generate_docx_report(data, risk_level, risk_emoji, lang, file_path)
            doc_file = FSInputFile(file_path, filename=file_name)
        except Exception as e:
            logger.error(f"Error generating Word report: {e}", exc_info=True)

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

        # Hujjatni yuborish
        if doc_file:
            caption_text = {
                "uz": "📄 Kengaytirilgan audit hisoboti (Microsoft Word formatida)",
                "ru": "📄 Расширенный отчет по аудиту (в формате Microsoft Word)",
                "en": "📄 Extended audit report (Microsoft Word format)",
            }.get(lang, "📄 Extended audit report")
            
            await message.answer_document(doc_file, caption=caption_text)


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
        try:
            target_user = int(payload.get("user_id"))
        except (ValueError, TypeError):
            logger.error(f"Invalid target user ID: {payload.get('user_id')}")
            return
        
        if action == "toggle_admin":
            new_status = toggle_admin(target_user)
            status_text = "Admin qilingan" if new_status else "Adminlikdan olingan"
            await message.answer(f"✅ Foydalanuvchi ({target_user}) {status_text}.")
        elif action == "edit_alias":
            new_alias = payload.get("alias")
            if new_alias:
                update_alias(target_user, new_alias)
                await message.answer(f"✅ Foydalanuvchi ({target_user}) taxallusi `{new_alias}` ga o'zgartirildi.", parse_mode=ParseMode.MARKDOWN)
        elif action == "approve":
            from database import approve_user
            approve_user(target_user, True)
            await message.answer(f"✅ Foydalanuvchi ({target_user}) tasdiqlandi (Approved).")
        elif action == "disapprove":
            from database import approve_user
            approve_user(target_user, False)
            await message.answer(f"❌ Foydalanuvchi ({target_user}) arizasi rad etildi/tasdiqdan olindi.")
        elif action == "delete_user":
            from database import delete_user
            delete_user(target_user)
            await message.answer(f"🗑 Foydalanuvchi ({target_user}) bazadan butunlay o'chirildi.")
                
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
        BotCommand(command="risk", description="Risk darajasi haqida"),
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

    # Web serverni ishga tushirish
    try:
        from web_server import start_web_server
        await start_web_server()
    except Exception as e:
        logger.error(f"Web serverni ishga tushirishda xatolik: {e}")

    logger.info("🛡 Crypto Threat Watch Bot ishga tushdi!")
    logger.info(f"Rate limit: {RATE_LIMIT_PER_MINUTE} so'rov/daqiqa")
    if WEBAPP_URL:
        logger.info(f"🌐 Web App: {WEBAPP_URL}")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
