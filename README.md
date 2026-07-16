# 🔍 Следопыт Crypto V2 / Sledopyt Crypto V2

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-blue.svg)](https://www.python.org/)
[![Telegram Bot](https://img.shields.io/badge/Telegram-Bot-26A5E4.svg)](https://t.me/Cryptop_q_bot)

---

## 🇷🇺 О проекте

**Следопыт** — Telegram-бот для крипто-трейдеров и инвесторов (РФ, СНГ).  
Детектор скамов и анализатор токенов: проверяет адреса, находит серийных мошенников,  
строит связи между кошельками и выдаёт риск-скор. Полностью бесплатно.

## 🇬🇧 About

**Sledopyt** is a Telegram bot for crypto traders and investors.  
A scam detector and token analyzer: checks wallet addresses, finds serial fraudsters,  
maps wallet connections, and outputs risk scores. Fully free to use.

---

## ✨ Features / Возможности

| Команда / Command | Описание / Description |
|---|---|
| `/investigate <address>` | 🕵️ Глубокое расследование токена — создатель, связи, siblings / Full token investigation — creator, wallet links, sibling tokens (free) |
| `/report <address>` | 🚨 Репорт скам-токена (подтверждение админом, +100 очков) / Report a scam token (admin review, +100 points) |
| `/hot` | 🔥 Горячие токены из DexScreener с риск-скором / Trending tokens from DexScreener with risk scoring |
| `/museum` | 🏛 Легендарные скам-кошельки / Legendary scam wallets collection |
| `/leaderboard` | 🏆 Топ охотников за скамом / Top scam reporters leaderboard |
| `/buy` | 💰 Покупка кредитов (скоро / coming soon) |

**Дополнительно / Extras:**
- 👥 **Реферальная система** — 10 кредитов другу, 20 рефереру / Referral system: 10 credits to friend, 20 to referrer
- 🎴 **PNG-карточки** для шеринга отчётов в Twitter / Share cards for reports
- 📅 **Ежедневный крон-пост** в канал с расследованием дня / Daily cron post to channel
- 🔥 **Геймификация** — стрики, достижения, очки / Gamification: streaks, achievements, points
- 🧠 **Semantic Parser** — понимает синонимы и фразы на естественном языке / Understands synonyms and natural language queries
- 🔗 **Multi-chain** — Ethereum, Solana, TON, Tron, BSC, Polygon, Base, Arbitrum

---

## 🚀 Quick Start / Быстрый старт

```bash
# 1. Клонируйте / Clone
git clone https://github.com/zad111ak-ai/sledopyt-crypto-v2.git
cd sledopyt-crypto-v2

# 2. Установите зависимости / Install deps
pip install aiogram httpx Pillow APScheduler python-dotenv

# 3. Создайте .env / Create .env
cat > .env << 'EOF'
SCAM_BOT_TOKEN=your_telegram_bot_token
ADMIN_ID=your_telegram_id
ETHERSCAN_API_KEY=your_key
ETHERSCAN_API_KEY_BSC=your_key
INVESTIGATIONS_CHANNEL=-100xxxxxxx
EOF

# 4. Запустите / Run
python bot.py
```

---

## 🛠 Tech Stack / Стек

| Компонент / Component | Технология / Technology |
|---|---|
| Язык / Language | Python 3.14 |
| Bot Framework | aiogram 3.x |
| База данных / Database | SQLite (WAL mode) |
| HTTP клиент / Client | httpx async |
| Изображения / Images | Pillow |
| Планировщик / Scheduler | APScheduler (cron jobs) |
| APIs | DexScreener, Etherscan, SolanaFM, TON |

---

## 📁 Структура проекта / Project Structure

```
├── bot.py                  # Главный файл бота / Main bot entry
├── db.py                   # SQLite база / Database layer
├── scanner.py              # Сканирование токенов / Token scanner
├── formatter.py            # Форматирование отчётов / Report formatting
├── semantic.py             # NLP-парсер / Natural language parser
├── address_parser.py       # Парсер адресов / Universal address parser
├── wallet_dna.py           # ДНК кошельков / Wallet fingerprinting
├── handlers/
│   ├── investigate.py      # /investigate
│   ├── scam_hunter.py      # /report, /leaderboard
│   ├── hot.py              # /hot
│   └── legends.py          # /museum
└── services/
    ├── detective/          # Расследователи / Investigation engine
    ├── visual/             # PNG-карточки / Share cards
    ├── legends/            # Музей скамов / Scam museum DB
    ├── gamification/       # Стрики и достижения / Streaks & achievements
    ├── payments/           # TON/CryptoBot оплаты / Payment processing
    ├── subscriptions/      # Канал и подписки / Channel manager
    ├── crypto/             # Wrapped-токены / Verified wrapped filter
    └── api/                # Умный маршрутизатор API / Smart API router
```

---

## ⚖️ License

[MIT](LICENSE) — используйте свободно / Use freely.

---

## 💝 Donations / Донаты

Если проект полезен — поддержите development / If useful — support development:

| Валюта / Currency | Адрес / Address |
|---|---|
| **BTC** | `bc1qd8sa7e4f696wmcyszuxh9snqt2n66zrhz9g80j` |
| **ETH** | `0xD26f0efE6A8F11e127c3Af3D6163BD458a1693c3` |
| **USDT (TON)** | `UQAoI2i8P9-JeZhvGSUwKnymVyY5cb-1Rg7pdqoWMNena7DP` |
| **SOL** | `99EtqBVTeF5UNp9a1oPi18iVXbXptTG7YQ6JeJvXMUJK` |

> 🇷🇺 *Каждый донат помогает добавить новые chain'ы и улучшить риск-скоринг.*  
> 🇬🇧 *Every donation helps add new chains and improve risk scoring.*

---

**🤖 Try it now: [@Cryptop_q_bot](https://t.me/Cryptop_q_bot)**
