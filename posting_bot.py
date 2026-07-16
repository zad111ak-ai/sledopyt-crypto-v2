#!/usr/bin/env python3
"""
Бот-привратник: принимает посты ТОЛЬКО от владельца,
публикует в канал. Безопасно — только owner_id может использовать.

Запуск:
  export POSTING_BOT_TOKEN='токен_бота'
  python3 posting_bot.py
"""

import asyncio
import logging
import os
import re
import sys
from collections import defaultdict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ─── Конфигурация ───
OWNER_ID = 405065016  # Joseph Postman
BOT_TOKEN = os.getenv("POSTING_BOT_TOKEN", "")

# Твои каналы: "@username канала": chat_id
# Узнать chat_id: добавь бота в канал, потом https://api.telegram.org/bot<TOKEN>/getUpdates
CHANNELS = {
    # "@my_channel": -1001234567890,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class PostStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_channel = State()


def is_owner(message_or_callback) -> bool:
    """Только OWNER_ID может пользоваться ботом."""
    if isinstance(message_or_callback, Message):
        user = message_or_callback.from_user
    elif isinstance(message_or_callback, CallbackQuery):
        user = message_or_callback.from_user
    else:
        return False
    return user and user.id == OWNER_ID


# ─── Команды ───

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not is_owner(message):
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.clear()
    await message.answer(
        "📝 <b>Бот-привратник</b>\n\n"
        "Присылай посты — я опубликую в канал.\n\n"
        "<b>Как использовать:</b>\n"
        "1. Напиши /post\n"
        "2. Скинь текст поста\n"
        "3. Выбери канал\n"
        "4. Готово!\n\n"
        "Команды:\n"
        "/post — создать пост\n"
        "/channels — список каналов\n"
        "/cancel — отмена"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if not is_owner(message):
        return
    await state.clear()
    await message.answer("❌ Отменено.")


@dp.message(Command("channels"))
async def cmd_channels(message: Message):
    if not is_owner(message):
        return
    if not CHANNELS:
        await message.answer("⚠️ Каналы не настроены.\nДобавь в CHANNELS в скрипте.")
        return
    lines = ["📢 <b>Каналы:</b>\n"]
    for name, cid in CHANNELS.items():
        lines.append(f"  • {name}\n    ID: <code>{cid}</code>")
    await message.answer("\n".join(lines))


@dp.message(Command("post"))
async def cmd_post(message: Message, state: FSMContext):
    if not is_owner(message):
        await message.answer("⛔ Доступ запрещён.")
        return
    await state.set_state(PostStates.waiting_for_text)
    await message.answer(
        "📝 <b>Отправь текст поста</b>\n\n"
        "Поддерживается:\n"
        "• <b>жирный</b> — &lt;b&gt;text&lt;/b&gt;\n"
        "• <i>курсив</i> — &lt;i&gt;text&lt;/i&gt;\n"
        "• <code>код</code> — &lt;code&gt;text&lt;/code&gt;\n"
        "• Списки, ссылки, эмодзи\n\n"
        "Или /cancel для отмены."
    )


@dp.message(PostStates.waiting_for_text)
async def process_text(message: Message, state: FSMContext):
    if not is_owner(message):
        return

    text = message.text or message.html_text or ""
    if len(text) < 5:
        await message.answer("⚠️ Слишком коротко. Минимум 5 символов.")
        return

    # Сохраняем текст в state
    await state.update_data(post_text=text)

    if not CHANNELS:
        await message.answer(
            "⚠️ Каналы не настроены.\n\n"
            "Добавь канал в CHANNELS:\n"
            'CHANNELS = {"@my_channel": -1001234567890}\n\n'
            "Узнать chat_id: добавь бота в канал → getUpdates"
        )
        await state.clear()
        return

    # Кнопки каналов
    buttons = []
    for name, cid in CHANNELS.items():
        buttons.append([InlineKeyboardButton(
            text=f"📢 {name}",
            callback_data=f"ch:{cid}"
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_post")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    preview = text[:300] + "..." if len(text) > 300 else text
    await message.answer(
        f"📝 <b>Предпросмотр:</b>\n\n"
        f"{preview}\n\n"
        f"📏 {len(text)} символов\n\n"
        "Выбери канал:",
        reply_markup=keyboard,
    )
    await state.set_state(PostStates.waiting_for_channel)


@dp.callback_query(F.data == "cancel_post")
async def cancel_post(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback):
        await callback.answer("⛔", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("❌ Публикация отменена.")
    await callback.answer()


@dp.callback_query(F.data.startswith("ch:"))
async def publish(callback: CallbackQuery, state: FSMContext):
    if not is_owner(callback):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    chat_id = int(callback.data.split(":", 1)[1])
    data = await state.get_data()
    post_text = data.get("post_text", "")

    if not post_text:
        await callback.message.edit_text("❌ Текст поста не найден. Начни заново: /post")
        await state.clear()
        await callback.answer()
        return

    await callback.message.edit_text("⏳ Публикация...")
    await callback.answer()

    try:
        await bot.send_message(
            chat_id=chat_id,
            text=post_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
        await callback.message.edit_text(f"✅ Опубликовано!")
        logger.info(f"Published to chat_id={chat_id}")
    except Exception as e:
        err = str(e)
        if "parse" in err.lower() or "entities" in err.lower():
            # Пробуем без HTML
            try:
                await bot.send_message(chat_id=chat_id, text=post_text)
                await callback.message.edit_text("✅ Опубликовано (без форматирования)!")
                return
            except Exception as e2:
                err = str(e2)
        await callback.message.edit_text(f"❌ Ошибка:\n<code>{err[:500]}</code>")
        logger.error(f"Publish error: {e}")

    await state.clear()


# ─── Запрет для чужих ───

@dp.message()
async def deny_all(message: Message):
    if not is_owner(message):
        user = message.from_user
        logger.warning(f"DENIED: user_id={user.id}, username={user.username}")
        await message.answer("⛔ Доступ запрещён.")


async def main():
    if not BOT_TOKEN:
        print("❌ Установи POSTING_BOT_TOKEN")
        print("   export POSTING_BOT_TOKEN='токен'")
        sys.exit(1)

    me = await bot.get_me()
    print(f"🤖 Бот: @{me.username} ({me.first_name})")
    print(f"👑 Owner: {OWNER_ID}")
    print(f"📢 Каналы: {list(CHANNELS.keys()) or '⚠️ не настроены'}")
    print("⏳ Polling...")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
