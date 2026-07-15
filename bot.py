#!/usr/bin/env python3
"""
sledopyt-crypto-v2 — Telegram бот с SemanticParser (всё на скриптах)
Понимает естественный язык: синонимы + fuzzy matching + иерархия.
"""

import os
from dotenv import load_dotenv
load_dotenv()
import re
import time
import asyncio
import logging
from typing import Dict

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession

import db
from utils.rate_limiter import rate_limiter
from scanner import scan_token, search_token, is_address, extract_address
from native_chains import smart_sort, is_wrapped, get_preferred_chains, force_native_chain
from services.gamification.streaks import update_streak
from services.payments.ton_native import PRODUCTS as TON_PRODUCTS, parse_payload as parse_ton_payload
from services.payments.ton_native import create_ton_invoice
from services.subscriptions.channel_manager import grant_access
from formatter import format_telegram_message, format_l1_report, format_comparison
from services.api.smart_router import router as api_router
from services.crypto.verified_wrapped import filter_wrapped
from services.api.http_client import HTTPClient
from utils.async_helpers import monitor_event_loop, api_limiter
from semantic import SemanticParser
from address_parser import UniversalAddressParser
import coingecko
from payment_handler import PaymentHandler

# ═══════════════════════════════════════════════════════════════════
#  НАСТРОЙКИ
# ═══════════════════════════════════════════════════════════════════
BOT_TOKEN = os.environ.get("SCAM_BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("SCAM_BOT_TOKEN must be set in .env!")
PROXY = os.environ.get("https_proxy", os.environ.get("HTTPS_PROXY", "http://127.0.0.1:1082"))
SCAN_COST = 1
DNA_COST = 5
FREE_CREDITS = 3
CRYPTOBOT_TOKEN = os.environ.get("CRYPTOBOT_TOKEN", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("bot")

# ═══════════════════════════════════════════════════════════════════
#  СЕМАНТИЧЕСКИЙ ПАРСЕР + АДРЕСНЫЙ ПАРСЕР
# ═══════════════════════════════════════════════════════════════════
parser = SemanticParser()
addr_parser = UniversalAddressParser()

# ═══════════════════════════════════════════════════════════════════
#  ТРАНСЛИТЕРАЦИЯ — кириллица → латиница (без внешних зависимостей)
# ═══════════════════════════════════════════════════════════════════

_TRANS_TABLE = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"yo",
    "ж":"zh","з":"z","и":"i","й":"y","к":"k","л":"l","м":"m",
    "н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u",
    "ф":"f","х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch",
    "ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
})


def translit_ru(text: str) -> str:
    """Транслитерация кириллицы в латиницу. PEPE/Швепс → PEPE/Schweppes."""
    return text.translate(_TRANS_TABLE) if any("а" <= c <= "я" for c in text.lower()) else text


def is_valid_query(text: str) -> bool:
    """Проверяет что запрос похож на название токена или адрес."""
    if len(text) < 1 or len(text) > 200:
        return False
    # Адреса (любой формат) — всегда ок
    if addr_parser.is_address(text):
        return True
    # URL — всегда ок
    if re.match(r'^https?://', text):
        return True
    # Латиница/кириллица + пробелы — ок
    if re.match(r'^[A-Za-zА-Яа-я0-9\s\-\$\.]+$', text):
        return True
    return False

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def ensure_user(uid: int, username: str = "") -> dict:
    user = db.get_user(uid)
    if username and username != user.get("username", ""):
        db.update_username(uid, username)
    if user["balance"] == 0 and user["total_scans"] == 0:
        db.add_balance(uid, FREE_CREDITS)
    return db.get_user(uid)


# ═══════════════════════════════════════════════════════════════════
#  КЛАВИАТУРЫ
# ═══════════════════════════════════════════════════════════════════

def kb_main(balance: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверить токен", callback_data="menu:search"),
         InlineKeyboardButton(text="🧬 DNA кошелька", callback_data="menu:dna_info")],
        [InlineKeyboardButton(text="🔥 Горячие токены", callback_data="menu:popular"),
         InlineKeyboardButton(text="⚔️ Сравнить", callback_data="menu:compare")],
        [InlineKeyboardButton(text="⭐ Watchlist", callback_data="menu:watchlist"),
         InlineKeyboardButton(text="🔔 Алерты", callback_data="menu:alerts")],
        [InlineKeyboardButton(text=f"💰 Баланс: {balance} кр.", callback_data="menu:balance"),
         InlineKeyboardButton(text="💎 Купить кредиты", callback_data="menu:deposit")],
        [InlineKeyboardButton(text="👥 Рефералка +10 кр.", callback_data="menu:referral"),
         InlineKeyboardButton(text="📚 Помощь", callback_data="menu:help")],
    ])


def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
    ])


def kb_deposit() -> InlineKeyboardMarkup:
    from cryptobot import PRICES
    btns = []
    for key, product in PRICES.items():
        btns.append([InlineKeyboardButton(
            text=f"💎 {product['description']} — {product['amount']} TON",
            callback_data=f"buy:{key}",
        )])
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def kb_search_results(results: list, query: str) -> InlineKeyboardMarkup:
    btns = []
    for pair in results[:5]:
        sym = pair.get("symbol", "?")
        chain = pair.get("chain", "?")
        addr = pair.get("address", "")
        liq = pair.get("liquidity", 0)
        liq_f = float(liq) if liq else 0
        liq_str = f"${liq_f/1e6:.1f}M" if liq_f >= 1e6 else f"${liq_f/1e3:.0f}K" if liq_f >= 1e3 else f"${liq_f:.0f}"
        btns.append([InlineKeyboardButton(
            text=f"{sym} ({chain}) | 💧{liq_str}",
            callback_data=f"scan:{addr}",
        )])
    btns.append([InlineKeyboardButton(text="❌ Отмена", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def kb_after_scan(address: str, risk: str, symbol: str = "", chain: str = "") -> InlineKeyboardMarkup:
    btns = []
    if risk in ("CRITICAL", "HIGH"):
        btns.append([InlineKeyboardButton(text="📋 Полный аудит", callback_data=f"paid:{address}")])
    if symbol:
        btns.append([InlineKeyboardButton(text="📊 В watchlist", callback_data=f"watch:add:{address}:{symbol}:{chain}")])
    btns.append([InlineKeyboardButton(text="📤 Шерить PNG", callback_data=f"share:{address}")])
    btns.append([InlineKeyboardButton(text="🔍 Проверить другой", callback_data="menu:search")])
    btns.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


def kb_unknown() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Проверить токен", callback_data="menu:search")],
        [InlineKeyboardButton(text="🧬 ДНК кошелька", callback_data="menu:dna_info")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:back")],
    ])


# ═══════════════════════════════════════════════════════════════════
#  ПОПУЛЯРНЫЕ ТОКЕНЫ
# ═══════════════════════════════════════════════════════════════════

POPULAR = [
    {"ticker": "PEPE", "chain": "ethereum"},
    {"ticker": "DOGE", "chain": "ethereum"},
    {"ticker": "SHIB", "chain": "ethereum"},
    {"ticker": "BONK", "chain": "solana"},
    {"ticker": "WIF", "chain": "solana"},
    {"ticker": "NOT", "chain": "ton"},
    {"ticker": "HMSTR", "chain": "ton"},
    {"ticker": "TURBO", "chain": "ethereum"},
]


def kb_popular() -> InlineKeyboardMarkup:
    btns = []
    row = []
    for i, t in enumerate(POPULAR):
        row.append(InlineKeyboardButton(text=t["ticker"], callback_data=f"pop:{t['ticker']}"))
        if len(row) == 3 or i == len(POPULAR) - 1:
            btns.append(row)
            row = []
    btns.append([InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(inline_keyboard=btns)


# ═══════════════════════════════════════════════════════════════════
#  AIOROUTER
# ═══════════════════════════════════════════════════════════════════
router = Router()

# ─── Подключение дополнительных хендлеров ─────────────────────
from handlers import legends as legends_handler
from handlers import investigate as investigate_handler
from handlers import scam_hunter as scam_hunter_handler
from apscheduler.schedulers.asyncio import AsyncIOScheduler

router.include_router(legends_handler.router)
router.include_router(investigate_handler.router)
router.include_router(scam_hunter_handler.router)

# ─── Cron: ежедневное расследование в канал ───────────────────
scheduler = AsyncIOScheduler()


async def _run_daily_investigation(bot_instance):
    from services.channel.daily_investigation import daily_investigation
    await daily_investigation(bot_instance)


# ─── /start ────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(m: Message):
    uid = m.from_user.id
    user = ensure_user(uid, m.from_user.username or "")
    bal = user["balance"]
    first_name = m.from_user.first_name or "друг"
    
    # Реферальный код из /start ABC123
    args = m.text.split(maxsplit=1)
    if len(args) > 1 and len(args[1]) <= 12:
        ref_code = args[1].strip()
        if db.register_referral(uid, ref_code):
            log.info("referral_registered user=%d code=%s", uid, ref_code)
    
    # Бонусное сообщение для новичков
    scans = user.get("total_scans", 0)
    if scans == 0:
        newbie = "🎁 Твоя первая проверка — <b>БЕСПЛАТНА!</b>\nПросто напиши название токена.\n\n"
    elif scans < 5:
        newbie = f"📈 Ты уже сделал {scans} проверок — продолжай!\n\n"
    else:
        newbie = ""
    
    await m.answer(
        f"🛡 <b>Привет, {first_name}!</b>\n\n"
        f"Я — <b>Крипто_Следопыт</b>, твой персональный аналитик.\n"
        f"Проверю любой токен на скам за 5 секунд.\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{newbie}"
        f"🎯 <b>Что я умею:</b>\n\n"
        f"🔍 Проверка токенов — скам или нет\n"
        f"🧬 DNA кошелька — анализ китов\n"
        f"🔥 Горячие токены — топ роста дня\n"
        f"⚔️ Сравнение — PEPE vs BONK\n"
        f"⭐ Watchlist — следи за токенами\n"
        f"🔔 Алерты — уведомления о цене\n"
        f"🏛 Легенды — адреса Сатоши, Виталика\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 <b>Как начать:</b>\n"
        f"1️⃣ Просто напиши: <code>PEPE</code> или <code>Bitcoin</code>\n"
        f"2️⃣ Или адрес: <code>0x69825...</code>\n"
        f"3️⃣ Или нажми кнопку ниже 👇\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💎 Баланс: <b>{bal}</b> кредитов\n"
        f"💳 1 проверка = {SCAN_COST} кредит",
        reply_markup=kb_main(bal),
        parse_mode=ParseMode.HTML,
    )


# ─── Callback: Навигация ──────────────────────────────────────────

@router.callback_query(F.data == "menu:back")
async def cb_back(cq: CallbackQuery):
    user = ensure_user(cq.from_user.id)
    await cq.message.edit_text(
        f"🛡 <b>СЛЕДОПЫТ CRYPTO</b>\n\n"
        f"Просто напиши название токена — я проверю.\n"
        f"💰 Баланс: <b>{user['balance']}</b> кредитов",
        reply_markup=kb_main(user["balance"]),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(cq: CallbackQuery):
    await cq.message.edit_text(
        "❓ <b>Как работает Следопыт</b>\n\n"
        "<b>Проверка токена:</b>\n"
        "• Напиши: PEPE, HAMSTER, DOGE\n"
        "• Или: «проверь NOT»\n"
        "• Или скинь адрес 0x...\n"
        "• Или ссылку DexScreener\n\n"
        "<b>🌍 Адреса 15+ сетей:</b>\n"
        "• Bitcoin: 1... / 3... / bc1...\n"
        "• Ethereum: 0x...\n"
        "• TON: EQ... / UQ...\n"
        "• Tron: T...\n"
        "• Solana, Cardano, Ripple, Litecoin...\n\n"
        "<b>🏛 Легендарные адреса:</b>\n"
        "• Скинь адрес Сатоши, Виталика — покажу справку\n\n"
        "<b>ДНК-анализ кошелька:</b>\n"
        "• /dna 0x... — покажу паттерны кита\n\n"
        "<b>Что проверяется:</b>\n"
        "• 🔴 Honeypot — можно ли продать\n"
        "• 🔴 Бесконечный минт\n"
        "• 🟠 Налоги buy/sell\n"
        "• 🟠 Ликвидность lock\n"
        "• 🟡 Топ-10 холдеров\n\n"
        f"<b>Стоимость:</b> 1 скан = {SCAN_COST} кредит\n"
        f"💰 Баланс: <b>{db.get_balance(cq.from_user.id)}</b>",
        reply_markup=kb_back(),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data == "menu:balance")
async def cb_balance(cq: CallbackQuery):
    user = ensure_user(cq.from_user.id)
    await cq.message.edit_text(
        f"💰 <b>Твой баланс</b>\n\n"
        f"💎 Кредиты: <b>{user['balance']}</b>\n"
        f"🔍 Всего сканов: {user['total_scans']}\n\n"
        f"1 TON = 10 кредитов\n"
        f"1 скан = {SCAN_COST} кредит",
        reply_markup=kb_main(user["balance"]),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data == "menu:deposit")
async def cb_deposit(cq: CallbackQuery):
    await cq.message.edit_text(
        f"💳 <b>Пополнение</b>\n\n"
        f"1 TON = 10 кредитов\n"
        f"1 скан = {SCAN_COST} кредит\n\n"
        "Выбери пакет 👇",
        reply_markup=kb_deposit(),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cq: CallbackQuery):
    product_key = cq.data.split(":", 1)[1]
    uid = cq.from_user.id
    from cryptobot import PRICES
    if product_key not in PRICES:
        await cq.answer("❌ Неизвестный продукт", show_alert=True)
        return
    
    product = PRICES[product_key]
    await cq.answer("💳 Создаю инвойс...")
    await cq.message.edit_text(
        f"⏳ <b>Создаю инвойс...</b>\n\n"
        f"💎 {product['description']}\n"
        f"💰 {product['amount']} TON",
        parse_mode=ParseMode.HTML,
    )
    
    try:
        invoice = await payment.create_payment(uid, product_key)
        await cq.message.edit_text(
            f"💳 <b>Оплата</b>\n\n"
            f"💎 {product['description']}\n"
            f"💰 <b>{product['amount']} TON</b>\n\n"
            f"👇 Нажми кнопку для оплаты:\n"
            f"(Ссылка действует 1 час)\n\n"
            f"После оплаты кредиты поступят автоматически.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить", url=invoice["pay_url"])],
                [InlineKeyboardButton(text="🔄 Проверить", callback_data=f"check_invoice:{invoice['invoice_id']}")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:back")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        log.error("create_invoice failed: %s", e)
        bal = db.get_balance(uid)
        await cq.message.edit_text(
            f"❌ <b>Ошибка создания инвойса</b>\n\n"
            f"Попробуй позже или напиши /support",
            reply_markup=kb_main(bal),
            parse_mode=ParseMode.HTML,
        )


# ─── Проверка инвойса ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_invoice:"))
async def cb_check_invoice(cq: CallbackQuery):
    invoice_id = cq.data.split(":", 1)[1]
    uid = cq.from_user.id
    
    result = db.process_payment_idempotent(invoice_id)
    
    if result is None:
        await cq.answer("❌ Инвойс не найден", show_alert=True)
        return
    
    if result.get("success"):
        bal = db.get_balance(uid)
        if result.get("already_processed"):
            await cq.answer("✅ Уже оплачено!", show_alert=True)
        else:
            await cq.answer(f"✅ +{result['credits_added']} кредитов!", show_alert=True)
        
        await cq.message.edit_text(
            f"✅ <b>Оплата прошла!</b>\n\n"
            f"💎 +{result['credits_added']} кредитов\n"
            f"💰 Баланс: <b>{bal}</b>",
            reply_markup=kb_main(bal),
            parse_mode=ParseMode.HTML,
        )
    else:
        await cq.answer("⏳ Ещё не оплачено. Попробуй через минуту.", show_alert=True)


# ─── Реферальная программа ────────────────────────────────────────

@router.message(Command("ref"))
async def cmd_ref(m: Message):
    stats = db.get_referral_stats(m.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start={stats['code']}"
    
    await m.answer(
        f"👥 <b>РЕФЕРАЛЬНАЯ ПРОГРАММА</b>\n\n"
        f"🎁 Приглашай друзей — получай кредиты!\n\n"
        f"<b>Как это работает:</b>\n"
        f"1. Друг регистрируется по твоей ссылке\n"
        f"2. Друг делает первую оплату\n"
        f"3. Вы оба получаете <b>10 кредитов</b>\n\n"
        f"🔗 <b>Твоя ссылка:</b>\n"
        f"<code>{link}</code>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"• Приглашено: {stats['total_referred']}\n"
        f"• Оплатили: {stats['converted']} ✅\n"
        f"• В процессе: {stats['pending']} ⏳\n"
        f"• Заработано: {stats['earned_credits']} кредитов 💎",
        parse_mode=ParseMode.HTML,
    )


# ─── /help — подробная инструкция ──────────────────────────────────

@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(
        "📚 <b>ПОЛНАЯ ИНСТРУКЦИЯ</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>ПРОВЕРКА ТОКЕНОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "5 способов проверить токен:\n\n"
        "1️⃣ <b>По названию:</b> PEPE, Bitcoin, NOT\n"
        "2️⃣ <b>По тикеру:</b> $PEPE, $BTC\n"
        "3️⃣ <b>По адресу контракта:</b>\n"
        "   <code>0x6982508145454Ce...</code>\n"
        "4️⃣ <b>По ссылке DexScreener:</b>\n"
        "   https://dexscreener.com/...\n"
        "5️⃣ <b>Быстрая проверка:</b> /q PEPE\n\n"
        "<b>Что в отчёте:</b>\n"
        "✅ Цена, Market Cap, ликвидность\n"
        "✅ Количество холдеров\n"
        "✅ Возраст токена\n"
        "✅ Security check (honeypot, mint, LP lock)\n"
        "✅ Красные флаги с объяснениями\n"
        "✅ Итоговая оценка риска\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🧬 <b>DNA КОШЕЛЬКОВ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Команда: /dna 0x...\n\n"
        "<b>Что анализирует:</b>\n"
        "• Win Rate (процент прибыльных сделок)\n"
        "• Среднее время удержания\n"
        "• Паттерн: скальпер / свинг / холдер\n"
        "• Риски кошелька\n"
        "• Рекомендации\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 <b>АНАЛИТИКА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• /hot — топ растущих токенов за 24ч\n"
        "• /q TOKEN — быстрая проверка\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⭐ <b>WATCHLIST + АЛЕРТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "После проверки нажми:\n"
        "• ⭐ В watchlist — добавить\n"
        "• 🔔 +10% / -15% — алерт по цене\n\n"
        "Команды:\n"
        "• /watchlist — мой список\n"
        "• /alerts — мои алерты\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💎 <b>КРЕДИТЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "• 1 проверка = 1 кредит\n"
        "• DNA кошелька = 5 кредитов\n\n"
        "<b>Пакеты:</b>\n"
        "• 10 кр. = 1 TON\n"
        "• 50 кр. = 4.5 TON (-10%)\n"
        "• 200 кр. = 15 TON (-25%) 🔥\n\n"
        "/buy — магазин | /balance — баланс\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👥 <b>РЕФЕРАЛКА</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Пригласи друга — вы оба получите <b>10 кредитов</b>\n"
        "/ref — твоя ссылка\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 <b>ВСЕ КОМАНДЫ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/buy — купить кредиты\n"
        "/balance — баланс\n"
        "/hot — горячие токены\n"
        "/q TOKEN — быстрая проверка\n"
        "/dna ADDRESS — DNA кошелька\n"
        "/watchlist — мой watchlist\n"
        "/alerts — мои алерты\n"
        "/ref — рефералка\n\n"
        "💡 <b>Совет:</b> Начни с /hot — топ растущих токенов!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Туториал (3 шага)", callback_data="tutorial:step1")],
            [InlineKeyboardButton(text="💎 Тарифы и цены", callback_data="menu:deposit")],
            [InlineKeyboardButton(text="👥 Рефералка", callback_data="menu:referral")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:back")],
        ]),
        parse_mode=ParseMode.HTML,
    )



# ─── /vs СРАВНЕНИЕ ТОКЕНОВ ──────────────────────────────────────

@router.message(Command("vs"))
async def cmd_vs(m: Message, command: CommandObject):
    """Сравнивает два токена: /vs PEPE BONK"""
    if not command.args:
        await m.answer(
            "⚔️ <b>СРАВНЕНИЕ ТОКЕНОВ</b>\n\n"
            "Использование: <code>/vs TOKEN1 TOKEN2</code>\n\n"
            "Примеры:\n"
            "• <code>/vs PEPE BONK</code>\n"
            "• <code>/vs DOGE SHIB</code>\n"
            "• <code>/vs NOT TON</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    parts = command.args.strip().split()
    if len(parts) < 2:
        await m.answer("⚠️ Нужно 2 токена: <code>/vs PEPE BONK</code>", parse_mode=ParseMode.HTML)
        return

    token_a, token_b = parts[0].strip().upper(), parts[1].strip().upper()

    # Сообщение о поиске
    status_msg = await m.answer(f"🔍 Ищу <b>{token_a}</b> и <b>{token_b}</b>...", parse_mode=ParseMode.HTML)

    # Параллельный поиск обоих токенов
    try:
        results = await asyncio.gather(
            search_token(token_a),
            search_token(token_b),
            return_exceptions=True,
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка поиска: {e}")
        return

    data_a, data_b = results

    # Обработка ошибок
    if isinstance(data_a, Exception):
        await status_msg.edit_text(f"❌ Токен <b>{token_a}</b> не найден: {data_a}")
        return
    if isinstance(data_b, Exception):
        await status_msg.edit_text(f"❌ Токен <b>{token_b}</b> не найден: {data_b}")
        return

    if not data_a:
        await status_msg.edit_text(f"❌ Токен <b>{token_a}</b> не найден на DexScreener")
        return
    if not data_b:
        await status_msg.edit_text(f"❌ Токен <b>{token_b}</b> не найден на DexScreener")
        return

    # Берём лучший pair для каждого
    pair_a = data_a[0]
    pair_b = data_b[0]

    # Параллельный security scan обоих
    try:
        scans = await asyncio.gather(
            scan_token(pair_a.get("baseToken", {}).get("address", "")),
            scan_token(pair_b.get("baseToken", {}).get("address", "")),
            return_exceptions=True,
        )
    except Exception:
        scans = [{"assessment": {"risk_level": "unknown", "flags": []}}] * 2

    scan_a = scans[0] if not isinstance(scans[0], Exception) else {"assessment": {"risk_level": "unknown", "flags": []}}
    scan_b = scans[1] if not isinstance(scans[1], Exception) else {"assessment": {"risk_level": "unknown", "flags": []}}

    # Merge scan data into pair data
    pair_a_full = {**pair_a, "assessment": scan_a.get("assessment", {}), "liquidity_usd": pair_a.get("liquidity", {}).get("usd", 0), "volume_24h": pair_a.get("volume", {}).get("h24", 0), "market_cap": pair_a.get("marketCap", 0), "price_change_24h": pair_a.get("priceChange", {}).get("h24", 0)}
    pair_b_full = {**pair_b, "assessment": scan_b.get("assessment", {}), "liquidity_usd": pair_b.get("liquidity", {}).get("usd", 0), "volume_24h": pair_b.get("volume", {}).get("h24", 0), "market_cap": pair_b.get("marketCap", 0), "price_change_24h": pair_b.get("priceChange", {}).get("h24", 0)}

    # Форматируем и отправляем
    report = format_comparison(pair_a_full, pair_b_full)
    await status_msg.edit_text(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

# ─── Туториал (3 шага) ──────────────────────────────────────────

@router.callback_query(F.data == "tutorial:step1")
async def tutorial_step1(cq: CallbackQuery):
    await cq.message.edit_text(
        "🎬 <b>ТУТОРИАЛ — Шаг 1 из 3</b>\n\n"
        "Давай попробуем первую проверку!\n\n"
        "🎯 <b>Задание:</b> Проверь токен PEPE\n\n"
        "Это бесплатно для новичков\n"
        "и займёт всего 5 секунд.\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Проверить PEPE (бесплатно)", callback_data="tutorial:try_pepe")],
            [InlineKeyboardButton(text="⏭ Пропустить туториал", callback_data="tutorial:finish")],
        ]),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()

@router.callback_query(F.data == "tutorial:try_pepe")
async def tutorial_try_pepe(cq: CallbackQuery):
    await cq.answer("🎯 Отлично! Теперь добавь в watchlist 👇")
    await cq.message.edit_text(
        "🎬 <b>ТУТОРИАЛ — Шаг 2 из 3</b>\n\n"
        "Отлично! Ты сделал первую проверку 🎉\n\n"
        "🎯 <b>Задание:</b> Добавь PEPE в watchlist\n\n"
        "Теперь ты сможешь следить за ценой\n"
        "и получать уведомления.\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Добавить PEPE в watchlist", callback_data="tutorial:try_watch")],
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="tutorial:finish")],
        ]),
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data == "tutorial:try_watch")
async def tutorial_try_watch(cq: CallbackQuery):
    await cq.answer("✅ Добавлено! Последний шаг 👇")
    await cq.message.edit_text(
        "🎬 <b>ТУТОРИАЛ — Шаг 3 из 3</b>\n\n"
        "Почти готово! 🎯\n\n"
        "🎁 <b>Задание:</b> Получи реф-ссылку\n\n"
        "Пригласи друга — и вы оба получите\n"
        "<b>по 10 бесплатных кредитов</b> после\n"
        "его первой оплаты.\n\n"
        "Нажми кнопку ниже 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Получить реф-ссылку", callback_data="tutorial:try_ref")],
            [InlineKeyboardButton(text="✅ Завершить туториал", callback_data="tutorial:finish")],
        ]),
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data == "tutorial:try_ref")
async def tutorial_try_ref(cq: CallbackQuery):
    stats = db.get_referral_stats(cq.from_user.id)
    await cq.answer()
    await cq.message.edit_text(
        f"👥 <b>Твоя реф-ссылка:</b>\n\n"
        f"<code>https://t.me/{BOT_USERNAME}?start={stats['code']}</code>\n\n"
        f"Скопируй и отправь другу!\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 Задание выполнено! Нажми «Завершить» 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Завершить туториал", callback_data="tutorial:finish")],
        ]),
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data == "tutorial:finish")
async def tutorial_finish(cq: CallbackQuery):
    await cq.answer("🎉 Туториал пройден!")
    bal = db.get_balance(cq.from_user.id)
    await cq.message.edit_text(
        "🎉 <b>Поздравляю! Туториал пройден!</b>\n\n"
        "Теперь ты умеешь:\n"
        "✅ Проверять токены на скам\n"
        "✅ Следить за ними через watchlist\n"
        "✅ Приглашать друзей за бонусы\n\n"
        f"💎 Баланс: <b>{bal}</b> кредитов\n\n"
        "🚀 <b>Готов к большим делам!</b>\n\n"
        "Попробуй /hot — топ растущих токенов дня",
        reply_markup=kb_main(bal),
        parse_mode=ParseMode.HTML,
    )


# ─── Callback: Навигация по меню ─────────────────────────────────

@router.callback_query(F.data == "menu:compare")
async def cb_compare(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_text(
        "⚔️ <b>СРАВНЕНИЕ ТОКЕНОВ</b>\n\n"
        "Отправь два тикера через пробел:\n\n"
        "<code>PEPE BONK</code>\n"
        "<code>DOGE SHIB</code>\n"
        "<code>NOT TON</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Назад", callback_data="menu:back")],
        ]),
        parse_mode=ParseMode.HTML,
    )

@router.callback_query(F.data == "menu:watchlist")
async def cb_watchlist(cq: CallbackQuery):
    await cmd_watchlist(cq.message)
    await cq.answer()

@router.callback_query(F.data == "menu:alerts")
async def cb_alerts(cq: CallbackQuery):
    alerts = db.get_pending_alerts()
    user_alerts = [a for a in alerts if a.get("user_id") == cq.from_user.id]
    
    if not user_alerts:
        await cq.message.edit_text(
            "🔔 <b>Мои алерты</b>\n\n"
            "У тебя пока нет активных алертов.\n\n"
            "💡 После проверки токена нажми\n"
            "🔔 +10% или 🔔 -15% чтобы добавить.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Проверить токен", callback_data="menu:search")],
                [InlineKeyboardButton(text="🏠 Назад", callback_data="menu:back")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    else:
        lines = []
        for a in user_alerts[:10]:
            sym = a.get("token_symbol", "?")
            rule = a.get("rule_type", "?")
            val = a.get("rule_value", 0)
            lines.append(f"• {sym}: {rule} {val:.0f}%")
        await cq.message.edit_text(
            "🔔 <b>Мои алерты</b>\n\n" + "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Назад", callback_data="menu:back")],
            ]),
            parse_mode=ParseMode.HTML,
        )
    await cq.answer()

@router.callback_query(F.data == "menu:referral")
async def cb_referral(cq: CallbackQuery):
    await cmd_ref(cq.message)
    await cq.answer()

# ─── Популярные ───────────────────────────────────────────────────

@router.callback_query(F.data == "menu:popular")
async def cb_popular(cq: CallbackQuery):
    await cq.message.edit_text(
        "🔥 <b>Популярные токены</b>\n\nВыбери для быстрой проверки 👇",
        reply_markup=kb_popular(),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data.startswith("pop:"))
async def cb_popular_scan(cq: CallbackQuery):
    ticker = cq.data.split(":", 1)[1]
    uid = cq.from_user.id
    user = ensure_user(uid)

    if user["balance"] < SCAN_COST:
        await cq.message.edit_text(
            f"⚠️ Недостаточно кредитов\n\n"
            f"Баланс: {user['balance']} | Нужно: {SCAN_COST}",
            reply_markup=kb_deposit(),
            parse_mode=ParseMode.HTML,
        )
        await cq.answer()
        return

    await cq.answer(f"Ищу {ticker}...")
    await cq.message.edit_text(f"🔍 Ищу <b>{ticker}</b>...", parse_mode=ParseMode.HTML)

    results = await search_token(ticker)

    # ЖЕСТКИЙ МАППИНГ: фильтруем по нативной сети
    forced_chain = force_native_chain(ticker)
    wrapped_warning = ""
    if forced_chain and results:
        native_results = [r for r in results if r.get("chain", "") == forced_chain]
        if native_results:
            results = [max(native_results, key=lambda x: float(x.get("liquidity", 0) or 0))]
        else:
            results = smart_sort(results, ticker)
            wrapped_warning = f"Это wrapped версия. Настоящий {ticker} на сети {forced_chain}"
    elif results:
        results = smart_sort(results, ticker)

    if results:
        if len(results) == 1:
            addr = results[0].get("address", "")
            await _do_scan(cq.message, uid, addr, wrapped_warning=wrapped_warning)
        else:
            await cq.message.edit_text(
                f"🎯 Найдено <b>{len(results)}</b> токенов по «{ticker}»\n\nВыбери 👇",
                reply_markup=kb_search_results(results, ticker),
                parse_mode=ParseMode.HTML,
            )
    else:
        await cq.message.edit_text(
            f"❌ «{ticker}» не найден\n\nПопробуй другой тикер или скинь адрес 0x...",
            reply_markup=kb_back(),
            parse_mode=ParseMode.HTML,
        )


# ─── Поиск ────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:search")
async def cb_search(cq: CallbackQuery):
    await cq.message.edit_text(
        "🔍 <b>Отправь название или адрес</b>\n\n"
        "• Название: PEPE, HAMSTER\n"
        "• Адрес: 0x69825...\n"
        "• Ссылку: dexscreener.com/...",
        reply_markup=kb_back(),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data == "menu:dna_info")
async def cb_dna_info(cq: CallbackQuery):
    await cq.message.edit_text(
        "🧬 <b>ДНК-анализ кошелька</b>\n\n"
        "Покажу паттерны кита:\n"
        "• Win rate, средний холд, предупреждения\n\n"
        "Отправь: /dna 0x...",
        reply_markup=kb_back(),
        parse_mode=ParseMode.HTML,
    )
    await cq.answer()


@router.callback_query(F.data.startswith("scan:"))
async def cb_scan(cq: CallbackQuery):
    address = cq.data.split(":", 1)[1]
    uid = cq.from_user.id
    await cq.answer("🔬 Сканирую...")
    await _do_scan(cq.message, uid, address)


@router.callback_query(F.data.startswith("watch:add:"))
async def cb_watch_add(cq: CallbackQuery):
    parts = cq.data.split(":")
    if len(parts) < 5:
        await cq.answer("Ошибка", show_alert=True)
        return
    _, _, address, symbol, chain = parts
    uid = cq.from_user.id
    ok = db.add_to_watchlist(uid, address, symbol, chain)
    if ok:
        await cq.answer(f"✅ {symbol} добавлен в watchlist", show_alert=True)
    else:
        await cq.answer("❌ Лимит 5 токенов. Удали старые: /watchlist", show_alert=True)


# ─── /dna WALLET ──────────────────────────────────────────────────

@router.message(Command("dna"))
async def cmd_dna(m: Message):
    """DNA кошелька — честное признание 'скоро'."""
    uid = m.from_user.id
    user = ensure_user(uid)

    # Если уже с аргументом — возвращаем кредиты
    parts = m.text.split(maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        # Возвращаем кредиты за DNA
        db.add_balance(uid, 5, "Возврат за DNA (скоро)")
        db.log_credit_transaction(uid, 5, "refund", "Возврат за DNA — скоро")

    await m.answer(
        "🧬 <b>DNA кошелька — скоро</b>\n\n"
        "Работаем над интеграцией с:\n"
        "• Helius (Solana)\n"
        "• Etherscan (Ethereum)\n"
        "• Toncenter (TON)\n\n"
        "Пока используй:\n"
        "• solscan.io\n"
        "• etherscan.io\n"
        "• tonviewer.com\n\n"
        "💰 Возвращаю 5 кредитов",
        parse_mode=ParseMode.HTML,
    )


# ═══════════════════════════════════════════════════════════════════
#  CORE: СКАНИРОВАНИЕ
# ═══════════════════════════════════════════════════════════════════

# ─── ERROR MESSAGES ───────────────────────────────────────────
ERROR_MESSAGES = {
    "token_not_found": (
        "❌ <b>Токен не найден</b>\n\n"
        "Причины:\n"
        "• Слишком новый (< 1 часа)\n"
        "• Низкая ликвидность\n"
        "• Опечатка в названии\n\n"
        "Попробуй:\n"
        "1. Проверь на CoinGecko\n"
        "2. Вставь адрес контракта\n"
        "3. Подожди 5 минут"
    ),
    "api_timeout": (
        "⏱ <b>API не отвечает</b>\n\n"
        "Попробуй через 1-2 минуты.\n"
        "Или другой токен."
    ),
    "api_error": (
        "⚠️ <b>Ошибка проверки</b>\n\n"
        "Попробуй позже.\n"
        "Если повторяется — /support"
    ),
}

async def _do_scan(message: types.Message, uid: int, address: str, wrapped_warning: str = ""):
    user = ensure_user(uid)

    if user["balance"] < SCAN_COST:
        await message.edit_text(
            f"⚠️ Недостаточно кредитов\n\n"
            f"Баланс: <b>{user['balance']}</b> | Нужно: {SCAN_COST}",
            reply_markup=kb_deposit(),
            parse_mode=ParseMode.HTML,
        )
        return

    db.spend_balance(uid, SCAN_COST)
    db.log_credit_transaction(uid, SCAN_COST, "spend", "Проверка токена")

    # Progress indicator
    status = await message.edit_text(
        "⏳ <b>Проверяю...</b>\n"
        "✅ Баланс проверен\n"
        "📊 Данные (1/3)",
        parse_mode=ParseMode.HTML,
    )

    start = time.time()
    try:
        result = await asyncio.wait_for(scan_token(address), timeout=30)
    except asyncio.TimeoutError:
        db.add_balance(uid, SCAN_COST)
        db.log_credit_transaction(uid, SCAN_COST, "refund", "Таймаут сканирования")
        await status.edit_text(ERROR_MESSAGES["api_timeout"], reply_markup=kb_back())
        return
    except Exception as e:
        log.error(f"Scan error: {e}")
        db.add_balance(uid, SCAN_COST)
        db.log_credit_transaction(uid, SCAN_COST, "refund", "Возврат за ошибку сканирования")
        await status.edit_text(ERROR_MESSAGES["api_error"], reply_markup=kb_back())
        return

    elapsed = int((time.time() - start) * 1000)

    if not result.get("success"):
        db.add_balance(uid, SCAN_COST)
        await status.edit_text(ERROR_MESSAGES["token_not_found"], reply_markup=kb_back())
        return

    risk = result.get("assessment", {}).get("risk_level", "unknown")
    db.record_scan(uid, address, risk, elapsed)

    # Gamification: streaks + achievements
    is_scam = risk in ("high", "critical")
    streak_info = update_streak(db._conn(), uid, is_scam)
    if streak_info["bonus"] > 0:
        db.add_balance(uid, streak_info["bonus"], f"Streak {streak_info['streak']}")
    for ach in streak_info.get("new_achievements", []):
        db.add_balance(uid, ach["reward"], ach["name"])

    msg = format_telegram_message(result, wrapped_warning)
    symbol = result.get("symbol", "")
    chain = result.get("chain", "")

    await status.edit_text(
        msg,
        reply_markup=kb_after_scan(address, risk.upper(), symbol, chain),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


# ─── /watchlist ─────────────────────────────────────────────────

@router.message(Command("watchlist"))
async def cmd_watchlist(m: Message):
    uid = m.from_user.id
    items = db.get_watchlist(uid)
    if not items:
        await m.answer(
            "📊 <b>Твой watchlist пуст</b>\n\n"
            "После проверки токена нажми «📊 В watchlist»\n"
            "Лимит: 5 токенов (бесплатно)",
            parse_mode=ParseMode.HTML,
        )
        return
    lines = ["📊 <b>Твой Watchlist:</b>\n"]
    for i, item in enumerate(items, 1):
        sym = item.get("token_symbol", "?")
        chain = item.get("chain", "?")
        addr = item.get("token_address", "")[:16]
        lines.append(f"{i}. <b>{sym}</b> ({chain})")
        lines.append(f"   <code>{addr}...</code>")
    lines.append(f"\nЛимит: {len(items)}/5")
    await m.answer("\n".join(lines), parse_mode=ParseMode.HTML)

@router.message(Command("unwatch"))
async def cmd_unwatch(m: Message):
    parts = m.text.split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Отправь: /unwatch PEPE", parse_mode=ParseMode.HTML)
        return
    query = parts[1].strip().upper()
    uid = m.from_user.id
    items = db.get_watchlist(uid)
    for item in items:
        if item.get("token_symbol", "").upper() == query:
            db.remove_from_watchlist(uid, item["token_address"])
            await m.answer(f"✅ {query} удалён из watchlist")
            return
    await m.answer(f"❌ {query} не найден в watchlist")


# ═══════════════════════════════════════════════════════════════════
#  SEMANTIC ROUTER — обрабатывает ЛЮБОЙ текст через SemanticParser
# ═══════════════════════════════════════════════════════════════════

@router.message(F.text)
async def handle_any_text(m: Message):
    # Rate limiting
    allowed, wait_s = rate_limiter.check(m.from_user.id, max_per_minute=10)
    if not allowed:
        await m.answer(
            f"⏳ Слишком много запросов! Подожди {wait_s} сек.\n\n💡 Лимит: 10 запросов в минуту.",
            parse_mode=ParseMode.HTML,
        )
        return
    text = m.text.strip()
    if not text or text.startswith("/"):
        return

    # Валидация + транслитерация кириллицы
    if not is_valid_query(text):
        # Умные подсказки на основе текста
        hints = []
        if len(text) <= 20 and text.replace(" ", "").isalnum():
            hints.append(f"💡 Похоже на токен? Попробуй: /q {text}")
        if len(text) > 20 and any(c.isdigit() for c in text):
            hints.append(f"💡 Это похоже на адрес? Попробуй: /dna {text[:20]}...")
        
        hints_text = "\n".join(hints) if hints else ""
        if hints_text:
            hints_text += "\n\n"
        
        await m.answer(
            f"🤔 «{text[:30]}» не совсем понял тебя\n\n"
            f"{hints_text}"
            "💡 <b>Что я умею:</b>\n"
            "• Проверять токены (просто напиши PEPE)\n"
            "• Анализировать кошельки (/dna 0x...)\n"
            "• Горячие токены (/hot)\n"
            "• Сравнивать (/vs PEPE BONK)",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Проверить токен", callback_data="menu:search"),
                 InlineKeyboardButton(text="🔥 Горячие токены", callback_data="menu:popular")],
                [InlineKeyboardButton(text="📚 Справка", callback_data="menu:help"),
                 InlineKeyboardButton(text="🏠 Меню", callback_data="menu:back")],
            ]),
            parse_mode=ParseMode.HTML,
        )
        return

    text = translit_ru(text)

    # ─── АДРЕС: Универсальный парсинг (15+ блокчейнов) ──────────
    parsed_addr = addr_parser.parse(text)
    if parsed_addr:
        addr = parsed_addr.address
        chain = parsed_addr.chain
        hist = parsed_addr.historical_info

        # Проверка на легенду из Музея
        from handlers.legends import check_legend
        legend_card = check_legend(addr)
        if legend_card:
            await m.answer(legend_card, parse_mode=ParseMode.HTML)
            return

        # Легендарный адрес → красивая справка
        if parsed_addr.is_historical and hist:
            report = (
                f"🏛 <b>{hist.get('name', 'Исторический адрес')}</b>\n\n"
                f"👤 Владелец: <b>{hist.get('owner', 'Неизвестен')}</b>\n\n"
                f"📖 {hist.get('info', '')}\n\n"
                f"🔗 <code>{addr}</code>\n"
                f"⛓ Сеть: <b>{chain.upper()}</b>\n"
                f"🏷 Значимость: <b>{hist.get('significance', 'historical').upper()}</b>"
            )
            if hist.get("balance_note"):
                report += f"\n💰 {hist['balance_note']}"
            report += (
                "\n\n💡 _Это один из самых известных адресов в крипто-истории_"
            )
            await m.answer(report, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            return

        # BTC / LTC / XRP — UTXO, только анализ кошелька
        if chain in ("bitcoin", "litecoin", "ripple", "stellar"):
            user = ensure_user(uid, m.from_user.username or "")
            if user["balance"] < SCAN_COST:
                await m.answer(
                    f"⚠️ Недостаточно кредитов\n\n"
                    f"Баланс: <b>{user['balance']}</b> | Нужно: {SCAN_COST}",
                    reply_markup=kb_deposit(),
                    parse_mode=ParseMode.HTML,
                )
                return
            await m.answer(
                f"🔍 <b>Анализ {chain.upper()} кошелька...</b>\n"
                f"<code>{addr[:20]}...{addr[-8:]}</code>",
                parse_mode=ParseMode.HTML,
            )
            # Пока — DexScreener попытка (для wrapped версий)
            results = await search_token(addr)
            if results:
                await _do_scan(m, uid, results[0].get("address", addr))
            else:
                await m.answer(
                    f"📊 <b>{chain.upper()} адрес</b>\n"
                    f"<code>{addr}</code>\n\n"
                    f"⛓ Сеть: {chain}\n"
                    f"📝 Тип: {parsed_addr.format_subtype}\n\n"
                    f"💡 _Анализ UTXO-кошельков через API в разработке_",
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
            return

        # TON / TRON — анализ кошелька через API
        if chain in ("ton", "tron"):
            user = ensure_user(uid, m.from_user.username or "")
            if user["balance"] < SCAN_COST:
                await m.answer(
                    f"⚠️ Недостаточно кредитов\n\n"
                    f"Баланс: <b>{user['balance']}</b> | Нужно: {SCAN_COST}",
                    reply_markup=kb_deposit(),
                    parse_mode=ParseMode.HTML,
                )
                return
            # Пробуем scan_token (через chain-specific API)
            await _do_scan(m, uid, addr)
            return

        # ETH / SOL / BSC / EVM — scan через DexScreener/GoPlus
        if chain in ("ethereum", "solana", "ton", "tron"):
            await _do_scan(m, uid, addr)
            return

        # Остальные сети (Cardano, Cosmos, NEAR, Tezos, Hedera...)
        await m.answer(
            f"🔍 <b>{chain.upper()} адрес обнаружен</b>\n\n"
            f"<code>{addr}</code>\n\n"
            f"⛓ Сеть: <b>{chain}</b>\n"
            f"📝 Тип: {parsed_addr.format_subtype}\n\n"
            f"💡 _Анализ этой сети пока в разработке_",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        return

    intent = parser.parse(text)
    uid = m.from_user.id
    log.info(f"Intent: {intent.intent} ({intent.confidence:.1f}) — «{text[:40]}»")

    if intent.intent == "GREETING":
        user = ensure_user(uid, m.from_user.username or "")
        await m.answer(
            f"👋 Привет, {m.from_user.first_name}!\n\n"
            f"Просто напиши название токена — я проверю на скам.\n"
            f"💰 Баланс: <b>{user['balance']}</b> кредитов",
            reply_markup=kb_main(user["balance"]),
            parse_mode=ParseMode.HTML,
        )

    elif intent.intent == "HELP":
        user = ensure_user(uid)
        await m.answer(
            "❓ <b>Как пользоваться</b>\n\n"
            "Просто напиши название токена:\n"
            "• PEPE, HAMSTER, DOGE, NOT\n"
            "• «проверь BONK»\n"
            "• Адрес: 0x...\n\n"
            "🧬 ДНК-анализ: /dna 0x...",
            reply_markup=kb_main(user["balance"]),
            parse_mode=ParseMode.HTML,
        )

    elif intent.intent == "SHOW_BALANCE":
        user = ensure_user(uid)
        await m.answer(
            f"💰 Баланс: <b>{user['balance']}</b> кредитов\n"
            f"🔍 Всего сканов: {user['total_scans']}",
            reply_markup=kb_main(user["balance"]),
            parse_mode=ParseMode.HTML,
        )

    elif intent.intent == "DEPOSIT":
        await m.answer(
            "💳 <b>Пополнение</b>\n\nВыбери пакет 👇",
            reply_markup=kb_deposit(),
            parse_mode=ParseMode.HTML,
        )

    elif intent.intent == "SCAN":
        addr = intent.entities.get("wallet") or intent.entities.get("token_address", "")
        if addr:
            await _do_scan(m, uid, addr)
        else:
            await m.answer(
                "🤔 Не смог извлечь адрес\n\n"
                "Попробуй: 0x6982508145454Ce325dDbE47a25d4ec3d2311933",
                reply_markup=kb_unknown(),
                parse_mode=ParseMode.HTML,
            )

    elif intent.intent in ("TOKEN_ANALYSIS", "RUG_CHECK", "BUY_DECISION", "EXIT_STRATEGY"):
        token = intent.entities.get("token_symbol") or intent.entities.get("token_address", "")
        query = token or text
        user = ensure_user(uid, m.from_user.username or "")

        if user["balance"] < SCAN_COST:
            await m.answer(
                f"⚠️ Недостаточно кредитов\n\n"
                f"Баланс: <b>{user['balance']}</b> | Нужно: {SCAN_COST}",
                reply_markup=kb_deposit(),
                parse_mode=ParseMode.HTML,
            )
            return

        # ─── L1 ТОКЕН? → CoinGecko + wrapped ────────────────────
        if coingecko.is_l1_token(query):
            status = await m.answer(f"🔍 Ищу <b>{query}</b> (CoinGecko)...", parse_mode=ParseMode.HTML)
            l1_data = await coingecko.get_coin_data(query)

            if l1_data:
                # Ищем wrapped версии на DEX
                dex_results = await search_token(query)
                forced_chain = force_native_chain(query)
                wrapped_list = []
                if dex_results:
                    # Фильтруем wrapped (не на родной сети)
                    raw_wrapped = [r for r in dex_results if r.get("chain", "") != forced_chain]
                    # Фильтруем скам-клоны: только верифицированные + цена ±15%
                    orig_price = float(l1_data.get("market_data", {}).get("current_price", {}).get("usd", 0))
                    wrapped_list = filter_wrapped(orig_price, raw_wrapped)
                    wrapped_list = smart_sort(wrapped_list, query)[:3]

                report = format_l1_report(l1_data, wrapped_list)
                await status.edit_text(report, parse_mode=ParseMode.HTML)
                db.add_balance(uid, -SCAN_COST)
                return
            else:
                # CoinGecko не ответил — fallback на DexScreener
                pass

        # ─── ОБЫЧНЫЙ ТОКЕН → DexScreener ─────────────────────────
        status = await m.answer(f"🔍 Ищу <b>{query}</b>...", parse_mode=ParseMode.HTML)
        results = await search_token(query)

        # ЖЕСТКИЙ МАППИНГ: фильтруем по нативной сети для известных токенов
        forced_chain = force_native_chain(query)
        if forced_chain and results:
            native_results = [r for r in results if r.get("chain", "") == forced_chain]
            if native_results:
                # Берем самый ликвидный из родной сети
                results = [max(native_results, key=lambda x: float(x.get("liquidity", 0) or 0))]
            else:
                # Если в родной сети нет - показываем первый результат с предупреждением
                results = smart_sort(results, query)
                if results:
                    results[0]["wrapped_warning"] = f"Это wrapped версия. Настоящий {query} на сети {forced_chain}"
        else:
            results = smart_sort(results, query)  # нативная сеть в приоритете

        if not results:
            await status.edit_text(
                f"❌ «{query}» не найден\n\n"
                "💡 Попробуй:\n"
                "• Другое написание\n"
                "• Адрес: 0x...\n"
                "• Ссылку DexScreener",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔍 DexScreener",
                                          url=f"https://dexscreener.com/search?q={query}")],
                    [InlineKeyboardButton(text="◀️ Меню", callback_data="menu:back")],
                ]),
                parse_mode=ParseMode.HTML,
            )
            return

        if len(results) == 1:
            addr = results[0].get("address", "")
            sym = results[0].get("symbol", "?")
            ww = results[0].get("wrapped_warning", "")
            await status.edit_text(f"🎯 Найден: <b>{sym}</b>", parse_mode=ParseMode.HTML)
            await _do_scan(status, uid, addr, wrapped_warning=ww)
        else:
            await status.edit_text(
                f"🎯 Найдено <b>{len(results)}</b> по «{query}»\n\nВыбери 👇",
                reply_markup=kb_search_results(results, query),
                parse_mode=ParseMode.HTML,
            )

    elif intent.intent == "WALLET_DNA":
        wallet = intent.entities.get("wallet", "")
        if not wallet:
            await m.answer(
                "🧬 Укажи адрес кошелька\n\nОтправь: /dna 0x...",
                reply_markup=kb_back(),
                parse_mode=ParseMode.HTML,
            )
        else:
            m.text = f"/dna {wallet}"
            await cmd_dna(m)

    else:
        # UNKNOWN — подсказки
        await m.answer(
            f"🤔 Не совсем понял\n\n"
            f"Ты написал: <i>{text[:60]}</i>\n\n"
            f"Попробуй:\n"
            f"• Название токена: PEPE, HAMSTER\n"
            f"• «проверь NOT»\n"
            f"• Адрес: 0x...\n"
            f"• /dna 0x... — анализ кошелька",
            reply_markup=kb_unknown(),
            parse_mode=ParseMode.HTML,
        )


# ─── /apistats АДМИН ──────────────────────────────────────

@router.message(Command("apistats"))
async def cmdapistats(m: Message):
    admin_id = int(os.environ.get("ADMIN_ID", "0"))
    if m.from_user.id != admin_id:
        await m.answer("⛔ Нет доступа")
        return

    stats = api_router.get_stats()
    lines = ["📊 API СТАТИСТИКА\n"]
    for name, s in sorted(stats.items(), key=lambda x: x[1]["total_requests"], reverse=True):
        health = "🟢" if s["is_healthy"] else "🔴"
        lines.append(f"{health} {name}: reqs={s["total_requests"]} errors={s["total_errors"]} ({s["error_rate"]}%) rate={s["rate_usage"]}")
    await m.answer("\n".join(lines))

@router.message(Command("buy"))
async def cmd_buy(m: Message, command: CommandObject):
    """Покупка кредитов через TON Space."""
    uid = m.from_user.id

    if command.args:
        product_key = command.args.strip().lower()
        product = TON_PRODUCTS.get(product_key)
        if not product:
            await m.answer(
                "❌ Неизвестный продукт\n\n"
                "Доступно:\n"
                "• /buy credits_10 — 10 кредитов (1 TON)\n"
                "• /buy credits_50 — 50 кредитов (4.5 TON)\n"
                "• /buy credits_200 — 200 кредитов (15 TON)\n"
                "• /buy pro_week — Pro на неделю (50 TON)\n"
                "• /buy pro_month — Pro на месяц (180 TON)",
                parse_mode=ParseMode.HTML,
            )
            return

        try:
            await create_ton_invoice(m.bot, uid, product_key)
        except Exception as e:
            log.error(f"Invoice error: {e}")
            await m.answer("❌ Ошибка создания инвойса. Попробуй позже.")
        return

    # Меню покупки
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 10 кредитов — 1 TON", callback_data="buy:credits_10")],
        [InlineKeyboardButton(text="💎 50 кредитов — 4.5 TON", callback_data="buy:credits_50")],
        [InlineKeyboardButton(text="💎 200 кредитов — 15 TON", callback_data="buy:credits_200")],
        [InlineKeyboardButton(text="👑 Pro неделя — 50 TON", callback_data="buy:pro_week")],
        [InlineKeyboardButton(text="👑 Pro месяц — 180 TON", callback_data="buy:pro_month")],
    ])

    await m.answer(
        "💳 <b>ПОКУПКА КРЕДИТОВ</b>\n\n"
        "Оплата через TON Space (без комиссии)\n\n"
        "Выбери пакет:",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(cq: CallbackQuery):
    """Обработка нажатия кнопки покупки."""
    product_key = cq.data.split(":", 1)[1]
    uid = cq.from_user.id

    try:
        await create_ton_invoice(cq.bot, uid, product_key)
        await cq.answer()
    except Exception as e:
        log.error(f"Invoice error: {e}")
        await cq.answer("❌ Ошибка", show_alert=True)


# ─── TON NATIVE PAYMENTS ──────────────────────────────────────

@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    """Подтверждаем оплату TON Space."""
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def on_ton_payment(m: Message):
    """Обработка успешной оплаты через TON Space."""
    payload = m.successful_payment.invoice_payload
    parsed = parse_ton_payload(payload)

    if not parsed:
        await m.answer("❌ Ошибка обработки оплаты")
        return

    user_id = parsed["user_id"]
    product_key = parsed["product_key"]
    product = TON_PRODUCTS.get(product_key)

    if not product:
        await m.answer("❌ Неизвестный продукт")
        return

    # Начисляем кредиты
    if product.get("credits"):
        db.add_balance(user_id, product["credits"], product["desc"])
        db.log_credit_transaction(user_id, product["credits"], "ton_payment", product["desc"])

    # Pro подписка
    if product.get("days"):
        days = product["days"]
        # Продлеваем pro
        db.extend_pro(user_id, days)
        # Выдаём доступ в канал
        await grant_access(m.bot, user_id, days)
        await m.answer(
            f"✅ *Pro активирован!*\n\n"
            f"🔗 Доступ в закрытый канал будет отправлен",
            parse_mode="Markdown",
        )

    amount_ton = m.successful_payment.total_amount / 1e9
    db.save_crypto_payment(
        invoice_id=payload,
        user_id=user_id,
        product=product_key,
        amount_ton=amount_ton,
        currency="TON",
    )

    await m.answer(
        f"✅ *Оплата получена!*\n\n"
        f"{product['desc']}\n"
        f"💰 Оплачено: {amount_ton} TON",
        parse_mode="Markdown",
    )

    log.info(f"TON payment: user={user_id} product={product_key} amount={amount_ton}")


# ─── SHARE PNG ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("share:"))
async def cb_share(cq: CallbackQuery):
    """Генерирует PNG-карточку для шеринга."""
    from services.visual.share_card import generate_report_card
    from aiogram.types import BufferedInputFile

    address = cq.data.split(":", 1)[1]

    # Запускаем скан для данных
    try:
        result = await scan_token(address)
    except Exception:
        await cq.answer("❌ Ошибка", show_alert=True)
        return

    if not result.get("success"):
        await cq.answer("❌ Токен не найден", show_alert=True)
        return

    assessment = result.get("assessment", {})
    token_data = {
        "symbol": result.get("symbol", "TOKEN"),
        "name": result.get("name", ""),
        "chain": result.get("chain", ""),
        "price": result.get("price", 0),
        "market_cap": result.get("market_cap", 0),
        "liquidity": result.get("liquidity", 0),
        "holders": result.get("holders", 0),
    }
    security = {
        "score": assessment.get("risk_score", 50),
        "flags": assessment.get("flags", []),
        "risk_level": assessment.get("risk_level", "unknown"),
    }

    img_bytes = generate_report_card(token_data, security)
    photo = BufferedInputFile(img_bytes, filename="report.png")

    await cq.message.answer_photo(
        photo=photo,
        caption=f"📊 ${token_data['symbol']} — Crypto Detective Report\n#CryptoScout #CryptoDetective",
    )
    await cq.answer()


# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════

async def main():
    if not BOT_TOKEN:
        print("❌ Задай SCAM_BOT_TOKEN")
        return

    db.init_db()

    # Payment handler
    payment = PaymentHandler(CRYPTOBOT_TOKEN)
    session = AiohttpSession(proxy=PROXY)
    bot = Bot(token=BOT_TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)

    # Startup: event loop monitor
    asyncio.create_task(monitor_event_loop())

    stats = db.get_bot_stats()
    log.info("🚀 Следопыт Crypto v2 запущен!")
    log.info(f"   Пользователей: {stats['total_users']}")
    log.info(f"   Сканов: {stats['total_scans']}")
    log.info(f"   Выручка: {stats['total_revenue_ton']} TON")

    try:
        await dp.start_polling(bot)
    finally:
        await HTTPClient.close()
        log.info("🛑 Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main())
