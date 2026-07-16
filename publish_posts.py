#!/usr/bin/env python3
"""
Публикация серии постов в Telegram-канал.
Использование:
  python3 publish_posts.py --channel @channel_name
  python3 publish_posts.py --channel -1001234567890
  python3 publish_posts.py --discover   # найти каналы бота
"""
import asyncio
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

# === CONFIG ===
CONTENT_DIR = Path(__file__).parent / "content" / "series_ai_agent"
IMAGES_DIR = CONTENT_DIR / "images"
POSTS = [
    (0, "00_manifest.md", "post0_manifest.jpg"),
    (1, "01_prepare_windows.md", "post1_bios.jpg"),
    (2, "02_install_wsl.md", "post2_nodejs.jpg"),
    (3, "03_install_hermes.md", "post3_hermes.jpg"),
    (4, "04_mimo_code.md", "post4_mimo.jpg"),
    (5, "05_troubleshooting.md", "post5_troubleshoot.jpg"),
    (6, "06_what_next.md", "post6_done.jpg"),
]

API_BASE = "https://api.telegram.org/bot{token}"
RATE_LIMIT_DELAY = 1.5  # секунды между сообщениями


def get_token():
    """Получить токен из env или .env файла."""
    token = os.environ.get("WB_DAYBOT_TOKEN") or os.environ.get("SCAM_BOT_TOKEN")
    if not token:
        # Пробуем .env файл
        env_path = Path(__file__).parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("WB_DAYBOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not token:
        print("❌ Установите WB_DAYBOT_TOKEN: export WB_DAYBOT_TOKEN='your_token'")
        sys.exit(1)
    return token


def api_call(token: str, method: str, data: dict = None, files: dict = None) -> dict:
    """Вызвать Telegram Bot API."""
    url = API_BASE.format(token=token) + "/" + method
    with httpx.Client(timeout=30) as client:
        if files:
            resp = client.post(url, data=data, files=files)
        else:
            resp = client.post(url, json=data)
        return resp.json()


async def discover_channels(token: str):
    """Найти каналы, где бот — админ."""
    print("🔍 Ищу каналы, где бот является администратором...")
    
    # Пробуем getUpdates чтобы найти каналы
    result = api_call(token, "getUpdates", {"limit": 100})
    if result.get("ok"):
        channels = set()
        for update in result["result"]:
            msg = update.get("channel_post") or update.get("message") or {}
            chat = msg.get("chat", {})
            if chat.get("type") == "channel":
                channels.add((chat["id"], chat.get("title", ""), chat.get("username", "")))
        
        if channels:
            print("\n📢 Каналы из update'ов:")
            for cid, title, uname in channels:
                print(f"  📌 {title} (@{uname}) → chat_id={cid}")
        else:
            print("  Каналы не найдены в update'ах.")
    
    print("\n💡 Чтобы добавить бота в канал:")
    print("   1. Откройте канал → Настройки → Администраторы")
    print("   2. Добавьте бота как администратора с правом публикации")
    print("   3. Убедитесь, что в канале включены комментарии")
    print("   4. Запустите: python3 publish_posts.py --channel @ваш_канал")


def read_post(post_num: int, filename: str) -> str:
    """Прочитать текст поста и убрать метку картинки."""
    fpath = CONTENT_DIR / filename
    text = fpath.read_text(encoding="utf-8")
    
    # Убираем строку с картинкой (она для справки, в Telegram картинка отдельно)
    lines = text.split("\n")
    filtered = []
    for line in lines:
        if line.strip().startswith("📸 `") and "images/" in line:
            continue
        filtered.append(line)
    
    return "\n".join(filtered).strip()


def send_photo_post(token: str, chat_id: str, text: str, image_path: str, 
                    disable_comments: bool = False) -> bool:
    """Отправить пост с картинкой."""
    url = API_BASE.format(token=token) + "/sendPhoto"
    
    # Telegram caption limit — 1024 символа для фото
    # Если текст длиннее — разбиваем на фото + текст
    if len(text) <= 1024:
        with open(image_path, "rb") as img:
            data = {
                "chat_id": chat_id,
                "caption": text,
                "parse_mode": "Markdown",
                "disable_notification": "false",
            }
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, data=data, files={"photo": img})
                result = resp.json()
    else:
        # Длинный текст — сначала фото с короткой подписью, потом текст отдельно
        short_text = text[:1000] + "..."
        with open(image_path, "rb") as img:
            data = {
                "chat_id": chat_id,
                "caption": short_text,
                "parse_mode": "Markdown",
            }
            with httpx.Client(timeout=60) as client:
                resp = client.post(url, data=data, files={"photo": img})
                result = resp.json()
        
        if result.get("ok"):
            time.sleep(RATE_LIMIT_DELAY)
            # Отправляем полный текст отдельным сообщением
            msg_url = API_BASE.format(token=token) + "/sendMessage"
            full_data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true",
            }
            with httpx.Client(timeout=30) as client:
                resp = client.post(msg_url, json=full_data)
                result = resp.json()
    
    if result.get("ok"):
        print(f"  ✅ Отправлено! msg_id={result['result']['message_id']}")
        return True
    else:
        print(f"  ❌ Ошибка: {result.get('description', 'unknown')}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Публикация постов в Telegram-канал")
    parser.add_argument("--channel", help="chat_id или @username канала")
    parser.add_argument("--discover", action="store_true", help="Найти каналы бота")
    parser.add_argument("--post", type=int, help="Опубликовать только пост N (0-6)")
    parser.add_argument("--dry-run", action="store_true", help="Показать без отправки")
    args = parser.parse_args()
    
    token = get_token()
    print(f"✅ Токен загружен")
    
    if args.discover:
        discover_channels(token)
        return
    
    if not args.channel:
        print("❌ Укажите канал: --channel @username или --channel -100...")
        print("   Или используйте --discover чтобы найти каналы")
        sys.exit(1)
    
    chat_id = args.channel
    posts_to_publish = POSTS if args.post is None else [POSTS[args.post]]
    
    print(f"\n📢 Канал: {chat_id}")
    print(f"📝 Постов к публикации: {len(posts_to_publish)}")
    print()
    
    success = 0
    for num, filename, img_name in posts_to_publish:
        print(f"━━━ Пост {num}: {filename} ━━━")
        
        text = read_post(num, filename)
        img_path = IMAGES_DIR / img_name
        
        if not img_path.exists():
            print(f"  ⚠️ Картинка не найдена: {img_path}")
            print(f"  📤 Отправляю без картинки...")
            # Отправляем без картинки
            msg_url = API_BASE.format(token=token) + "/sendMessage"
            data = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true",
            }
            with httpx.Client(timeout=30) as client:
                result = client.post(msg_url, json=data).json()
            if result.get("ok"):
                print(f"  ✅ Отправлено! msg_id={result['result']['message_id']}")
                success += 1
            else:
                print(f"  ❌ {result.get('description', 'unknown')}")
        else:
            if args.dry_run:
                print(f"  📸 {img_path.name} ({img_path.stat().st_size // 1024}KB)")
                print(f"  📝 Текст: {len(text)} символов")
                print(f"  ⏭️ Dry run — пропускаю отправку")
            else:
                if send_photo_post(token, chat_id, text, str(img_path)):
                    success += 1
        
        if not args.dry_run and num != posts_to_publish[-1][0]:
            print(f"  ⏳ Пауза {RATE_LIMIT_DELAY}с...")
            time.sleep(RATE_LIMIT_DELAY)
        print()
    
    print(f"{'='*40}")
    print(f"📊 Результат: {success}/{len(posts_to_publish)} успешно")


if __name__ == "__main__":
    main()
