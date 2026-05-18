# 📝 AI Agent Task List (Ish rejasining bajarilish jadvali)

AI Agent ushbu loyihani bosqichma-bosqich qurishi va har bir bosqich tugagach, ushbu fayldagi `[ ]` belgisini `[x]` ga o'zgartirishi kerak.

## 🟩 Phase 1: Loyiha Muhitini Sozlash
- [x] `requirements.txt` faylini yaratish (`aiogram`, `httpx`, `python-dotenv`).
- [x] `.env.example` shablon faylini yaratish.
- [x] `config.py` faylida atrof-muhit o'zgaruvchilarini xavfsiz yuklash tizimini yozish.

## 🟩 Phase 2: Havolalarni Tahlil Qilish (Link Parsing)
- [x] `utils.py` faylini ochish.
- [x] TONViewer havolalari uchun Regex shablonini yozish.
- [x] Etherscan havolalari uchun Regex shablonini yozish.
- [x] Tronscan havolalari uchun Regex shablonini yozish.
- [x] Havolani qabul qilib, (`Network`, `Address`) formatida qaytaradigan `parse_crypto_link(url)` funksiyasini yozish.

## 🟩 Phase 3: Blokcheyn API Integratsiyasi (`services/`)
- [x] TON tarmog'i uchun `tonapi.io` xizmatini integratsiya qilish (Kirim/chiqim nanotonlarni TON'ga o'girib hisoblash).
- [x] Ethereum tarmog'i uchun `etherscan.io` API integratsiyasini yozish.
- [x] TRON (USDT TRC-20) tranzaksiyalarini hisoblash mantiqini yozish.

## 🟩 Phase 4: Telegram Bot Interfeysi (`main.py`)
- [x] `/start` komandasini sozlash (Kiberxavfsizlik xodimlari uchun yo'riqnoma bilan).
- [x] Link kelganda "🔄 Havola tahlil qilinmoqda..." deb turuvchi vizual status xabarini chiqarish.
- [x] Hisob-kitob tugagach, javobni chiroyli va qulay Markdown jadval ko'rinishida formatlash.
- [x] Xatoliklarni ushlash (Catching exceptions) — noto'g'ri link yoki API ishlamay qolganda bot o'chib qolmasligini ta'minlash.

## 🟩 Phase 5: Yakuniy Tekshiruv va Test
- [x] Botni mahalliy muhitda test qilish.
- [ ] API limitlari va asinxron so'rovlar tezligini optimallashtirish.