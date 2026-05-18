"""Ko'p tilli matnlar — O'zbek, Rus, Ingliz. Professional standart."""

from typing import Any

TEXTS: dict[str, dict[str, str]] = {
    # Til tanlash
    "choose_language": {
        "uz": "🌐 *Tilni tanlang:*",
        "ru": "🌐 *Выберите язык:*",
        "en": "🌐 *Choose language:*",
    },

    # Ro'yxatdan o'tish
    "ask_alias": {
        "uz": (
            "🔐 *Ro'yxatdan o'tish*\n\n"
            "Iltimos, taxallusingizni kiriting.\n"
            "Bu sizning anonimligingizni ta'minlaydi.\n\n"
            "⚠️ _Minimal 3 belgi_"
        ),
        "ru": (
            "🔐 *Регистрация*\n\n"
            "Пожалуйста, введите ваш псевдоним.\n"
            "Это обеспечит вашу анонимность.\n\n"
            "⚠️ _Минимум 3 символа_"
        ),
        "en": (
            "🔐 *Registration*\n\n"
            "Please enter your alias.\n"
            "This ensures your anonymity.\n\n"
            "⚠️ _Minimum 3 characters_"
        ),
    },
    "alias_too_short": {
        "uz": "⚠️ Taxallus kamida 3 belgidan iborat bo'lishi kerak.",
        "ru": "⚠️ Псевдоним должен содержать минимум 3 символа.",
        "en": "⚠️ Alias must be at least 3 characters.",
    },
    "registered_success": {
        "uz": (
            "✅ *Muvaffaqiyatli ro'yxatdan o'tdingiz!*\n\n"
            "👤 Taxallus: `{alias}`\n"
            "🌐 Til: O'zbekcha\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Endi blokcheyn skaner havolasini yuboring.\n"
            "Yordam: /help"
        ),
        "ru": (
            "✅ *Регистрация успешна!*\n\n"
            "👤 Псевдоним: `{alias}`\n"
            "🌐 Язык: Русский\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Теперь отправьте ссылку блокчейн-сканера.\n"
            "Помощь: /help"
        ),
        "en": (
            "✅ *Registration successful!*\n\n"
            "👤 Alias: `{alias}`\n"
            "🌐 Language: English\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Now send a blockchain scanner link.\n"
            "Help: /help"
        ),
    },

    # Help / Yo'riqnoma
    "help": {
        "uz": (
            "🛡 *Crypto Threat Watch — Yordam*\n\n"
            "Kiberxavfsizlik bo'limi uchun professional\n"
            "hamyon audit va monitoring vositasi.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Qo'llab-quvvatlanadigan tarmoqlar:*\n\n"
            "🔹 *TON* — `tonviewer.com/<address>`\n"
            "🔹 *ETH* — `etherscan.io/address/<address>`\n"
            "🔹 *TRON* — `tronscan.org/#/address/<address>`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ *Buyruqlar:*\n\n"
            "/start — Botni qayta ishga tushirish\n"
            "/help — Ushbu yordam\n"
            "/language — Tilni o'zgartirish\n"
            "/mystats — Shaxsiy statistika\n"
            "/history — So'rovlar tarixi\n"
            "/admin — Admin panel\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *Bot imkoniyatlari:*\n"
            "• Hozirgi balans (real-time)\n"
            "• Kirim/Chiqim tahlili\n"
            "• Jami tranzaksiyalar hajmi\n"
            "• Token turlari bo'yicha guruhlash\n"
            "• Risk darajasi baholash\n"
            "• Audit tarixi saqlash"
        ),
        "ru": (
            "🛡 *Crypto Threat Watch — Помощь*\n\n"
            "Профессиональный инструмент аудита\n"
            "и мониторинга кошельков для отдела\n"
            "кибербезопасности.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Поддерживаемые сети:*\n\n"
            "🔹 *TON* — `tonviewer.com/<address>`\n"
            "🔹 *ETH* — `etherscan.io/address/<address>`\n"
            "🔹 *TRON* — `tronscan.org/#/address/<address>`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ *Команды:*\n\n"
            "/start — Перезапуск бота\n"
            "/help — Эта справка\n"
            "/language — Сменить язык\n"
            "/mystats — Личная статистика\n"
            "/history — История запросов\n"
            "/admin — Панель администратора\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *Возможности бота:*\n"
            "• Текущий баланс (real-time)\n"
            "• Анализ входящих/исходящих\n"
            "• Общий объём транзакций\n"
            "• Группировка по типам токенов\n"
            "• Оценка уровня риска\n"
            "• Сохранение истории аудитов"
        ),
        "en": (
            "🛡 *Crypto Threat Watch — Help*\n\n"
            "Professional wallet audit and monitoring\n"
            "tool for the Cybersecurity Department.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *Supported networks:*\n\n"
            "🔹 *TON* — `tonviewer.com/<address>`\n"
            "🔹 *ETH* — `etherscan.io/address/<address>`\n"
            "🔹 *TRON* — `tronscan.org/#/address/<address>`\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "⚙️ *Commands:*\n\n"
            "/start — Restart bot\n"
            "/help — This help\n"
            "/language — Change language\n"
            "/mystats — Personal statistics\n"
            "/history — Query history\n"
            "/admin — Admin panel\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *Bot capabilities:*\n"
            "• Current balance (real-time)\n"
            "• Income/Outcome analysis\n"
            "• Total transaction volume\n"
            "• Token type grouping\n"
            "• Risk level assessment\n"
            "• Audit history storage"
        ),
    },

    # Tahlil jarayoni
    "analyzing": {
        "uz": (
            "⏳ *Tahlil jarayonida...*\n\n"
            "🌐 Tarmoq: `{network}`\n"
            "📍 Manzil: `{short_addr}`\n\n"
            "⏱ _Blokcheyn ma'lumotlari yuklanmoqda..._"
        ),
        "ru": (
            "⏳ *Идёт анализ...*\n\n"
            "🌐 Сеть: `{network}`\n"
            "📍 Адрес: `{short_addr}`\n\n"
            "⏱ _Загрузка данных блокчейна..._"
        ),
        "en": (
            "⏳ *Analyzing...*\n\n"
            "🌐 Network: `{network}`\n"
            "📍 Address: `{short_addr}`\n\n"
            "⏱ _Loading blockchain data..._"
        ),
    },

    # Natija — asosiy
    "result_header": {
        "uz": (
            "🛡 *HAMYON AUDIT HISOBOTI*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🌐 *Tarmoq:* `{network}`\n"
            "📍 *Manzil:*\n`{address}`\n\n"
        ),
        "ru": (
            "🛡 *ОТЧЁТ АУДИТА КОШЕЛЬКА*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🌐 *Сеть:* `{network}`\n"
            "📍 *Адрес:*\n`{address}`\n\n"
        ),
        "en": (
            "🛡 *WALLET AUDIT REPORT*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "🌐 *Network:* `{network}`\n"
            "📍 *Address:*\n`{address}`\n\n"
        ),
    },
    "result_balance": {
        "uz": "💎 *Hozirgi balans:* `{current_balance}`\n\n",
        "ru": "💎 *Текущий баланс:* `{current_balance}`\n\n",
        "en": "💎 *Current balance:* `{current_balance}`\n\n",
    },
    "result_summary": {
        "uz": (
            "📊 *Tranzaksiya xulosasi:*\n"
            "┌─────────────────────────\n"
            "│ 📥 Kirim:       `{income}`\n"
            "│ 📤 Chiqim:      `{outcome}`\n"
            "│ 💰 Sof qoldiq:  `{net}`\n"
            "│ 🔄 Jami hajm:   `{volume}`\n"
            "│ 📋 Tranzaksiyalar: `{tx_count} ta`\n"
            "└─────────────────────────\n"
        ),
        "ru": (
            "📊 *Сводка транзакций:*\n"
            "┌─────────────────────────\n"
            "│ 📥 Приход:       `{income}`\n"
            "│ 📤 Расход:       `{outcome}`\n"
            "│ 💰 Чистый:       `{net}`\n"
            "│ 🔄 Общий объём:  `{volume}`\n"
            "│ 📋 Транзакции:   `{tx_count} шт`\n"
            "└─────────────────────────\n"
        ),
        "en": (
            "📊 *Transaction summary:*\n"
            "┌─────────────────────────\n"
            "│ 📥 Income:       `{income}`\n"
            "│ 📤 Outcome:      `{outcome}`\n"
            "│ 💰 Net:          `{net}`\n"
            "│ 🔄 Total volume: `{volume}`\n"
            "│ 📋 Transactions: `{tx_count}`\n"
            "└─────────────────────────\n"
        ),
    },
    "result_risk": {
        "uz": "\n{risk_emoji} *Risk darajasi:* `{risk_level}`\n",
        "ru": "\n{risk_emoji} *Уровень риска:* `{risk_level}`\n",
        "en": "\n{risk_emoji} *Risk level:* `{risk_level}`\n",
    },
    "result_tokens_header": {
        "uz": "\n🪙 *Tokenlar bo'yicha taqsimot:*\n━━━━━━━━━━━━━━━━━━━━━\n",
        "ru": "\n🪙 *Распределение по токенам:*\n━━━━━━━━━━━━━━━━━━━━━\n",
        "en": "\n🪙 *Token breakdown:*\n━━━━━━━━━━━━━━━━━━━━━\n",
    },
    "result_footer": {
        "uz": "\n━━━━━━━━━━━━━━━━━━━━━\n🕐 _Tahlil vaqti: {timestamp}_",
        "ru": "\n━━━━━━━━━━━━━━━━━━━━━\n🕐 _Время анализа: {timestamp}_",
        "en": "\n━━━━━━━━━━━━━━━━━━━━━\n🕐 _Analysis time: {timestamp}_",
    },

    # Xatoliklar
    "invalid_link": {
        "uz": (
            "⚠️ *Tanilmagan format*\n\n"
            "Quyidagilardan birini yuboring:\n\n"
            "📎 *Havola:*\n"
            "• `tonviewer.com/<address>`\n"
            "• `etherscan.io/address/<address>`\n"
            "• `tronscan.org/#/address/<address>`\n\n"
            "📝 *Yoki to'g'ridan-to'g'ri manzil:*\n"
            "• `UQ...` / `EQ...` — TON\n"
            "• `0x...` — Ethereum\n"
            "• `T...` — TRON\n\n"
            "Yordam: /help"
        ),
        "ru": (
            "⚠️ *Неизвестный формат*\n\n"
            "Отправьте одно из следующего:\n\n"
            "📎 *Ссылка:*\n"
            "• `tonviewer.com/<address>`\n"
            "• `etherscan.io/address/<address>`\n"
            "• `tronscan.org/#/address/<address>`\n\n"
            "📝 *Или адрес напрямую:*\n"
            "• `UQ...` / `EQ...` — TON\n"
            "• `0x...` — Ethereum\n"
            "• `T...` — TRON\n\n"
            "Помощь: /help"
        ),
        "en": (
            "⚠️ *Unrecognized format*\n\n"
            "Send one of the following:\n\n"
            "📎 *Link:*\n"
            "• `tonviewer.com/<address>`\n"
            "• `etherscan.io/address/<address>`\n"
            "• `tronscan.org/#/address/<address>`\n\n"
            "📝 *Or raw address:*\n"
            "• `UQ...` / `EQ...` — TON\n"
            "• `0x...` — Ethereum\n"
            "• `T...` — TRON\n\n"
            "Help: /help"
        ),
    },
    "api_error": {
        "uz": "❌ *API xatoligi*\n\n`{error}`\n\n_Iltimos, keyinroq urinib ko'ring._",
        "ru": "❌ *Ошибка API*\n\n`{error}`\n\n_Пожалуйста, попробуйте позже._",
        "en": "❌ *API Error*\n\n`{error}`\n\n_Please try again later._",
    },
    "rate_limited": {
        "uz": "⏳ *So'rovlar limiti*\n\nIltimos, bir oz kuting va qayta urinib ko'ring.",
        "ru": "⏳ *Лимит запросов*\n\nПожалуйста, подождите и попробуйте снова.",
        "en": "⏳ *Rate limited*\n\nPlease wait a moment and try again.",
    },

    # Admin
    "admin_prompt": {
        "uz": "🔑 *Admin autentifikatsiya*\n\nParolni kiriting:",
        "ru": "🔑 *Аутентификация администратора*\n\nВведите пароль:",
        "en": "🔑 *Admin authentication*\n\nEnter password:",
    },
    "admin_success": {
        "uz": (
            "✅ *Admin huquqi berildi!*\n\n"
            "Mavjud buyruqlar:\n"
            "/stats — Umumiy statistika\n"
            "/users — Foydalanuvchilar\n"
            "/audits — Oxirgi auditlar\n"
            "/broadcast — Xabar yuborish"
        ),
        "ru": (
            "✅ *Права администратора получены!*\n\n"
            "Доступные команды:\n"
            "/stats — Общая статистика\n"
            "/users — Пользователи\n"
            "/audits — Последние аудиты\n"
            "/broadcast — Рассылка"
        ),
        "en": (
            "✅ *Admin access granted!*\n\n"
            "Available commands:\n"
            "/stats — General statistics\n"
            "/users — Users\n"
            "/audits — Recent audits\n"
            "/broadcast — Broadcast message"
        ),
    },
    "admin_fail": {
        "uz": "❌ *Noto'g'ri parol.*",
        "ru": "❌ *Неверный пароль.*",
        "en": "❌ *Wrong password.*",
    },
    "not_admin": {
        "uz": "⛔ *Sizda admin huquqi yo'q.*",
        "ru": "⛔ *У вас нет прав администратора.*",
        "en": "⛔ *You don't have admin rights.*",
    },

    # Statistika
    "my_stats": {
        "uz": (
            "📊 *Shaxsiy statistika*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👤 Taxallus: `{alias}`\n"
            "🔍 So'rovlar: `{count} ta`\n"
            "📅 Ro'yxatdan: `{registered}`"
        ),
        "ru": (
            "📊 *Личная статистика*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👤 Псевдоним: `{alias}`\n"
            "🔍 Запросы: `{count} шт`\n"
            "📅 Регистрация: `{registered}`"
        ),
        "en": (
            "📊 *Personal statistics*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👤 Alias: `{alias}`\n"
            "🔍 Queries: `{count}`\n"
            "📅 Registered: `{registered}`"
        ),
    },
    "global_stats": {
        "uz": (
            "📈 *Umumiy statistika*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👥 Foydalanuvchilar: `{users}`\n"
            "🔍 Jami so'rovlar: `{queries}`\n"
            "📋 Jami auditlar: `{audits}`"
        ),
        "ru": (
            "📈 *Общая статистика*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👥 Пользователи: `{users}`\n"
            "🔍 Всего запросов: `{queries}`\n"
            "📋 Всего аудитов: `{audits}`"
        ),
        "en": (
            "📈 *General statistics*\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "👥 Users: `{users}`\n"
            "🔍 Total queries: `{queries}`\n"
            "📋 Total audits: `{audits}`"
        ),
    },

    # Til
    "language_changed": {
        "uz": "✅ Til o'zgartirildi: *O'zbekcha* 🇺🇿",
        "ru": "✅ Язык изменён: *Русский* 🇷🇺",
        "en": "✅ Language changed: *English* 🇬🇧",
    },

    # Tarix
    "history_header": {
        "uz": "📋 *So'rovlar tarixi:*\n━━━━━━━━━━━━━━━━━━━━━\n",
        "ru": "📋 *История запросов:*\n━━━━━━━━━━━━━━━━━━━━━\n",
        "en": "📋 *Query history:*\n━━━━━━━━━━━━━━━━━━━━━\n",
    },
    "history_empty": {
        "uz": "📭 Hali hech qanday so'rov yuborilmagan.",
        "ru": "📭 Запросов пока нет.",
        "en": "📭 No queries yet.",
    },

    # Ro'yxatdan o'tmagan
    "not_registered": {
        "uz": "⚠️ Avval /start buyrug'ini yuboring.",
        "ru": "⚠️ Сначала отправьте /start.",
        "en": "⚠️ Please send /start first.",
    },
}


def t(key: str, lang: str = "uz", **kwargs: Any) -> str:
    """Matnni til bo'yicha olish va formatlash."""
    text_dict = TEXTS.get(key, {})
    text = text_dict.get(lang, text_dict.get("uz", ""))
    if kwargs:
        text = text.format(**kwargs)
    return text
