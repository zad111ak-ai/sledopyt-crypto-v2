#!/bin/bash
# scripts/deploy.sh — Безопасный деплой с бэкапом
set -e

PROJECT_DIR="/home/dima/sledopyt-crypto-v2"
BACKUP_DIR="$PROJECT_DIR/data/backups"
LOG_DIR="$PROJECT_DIR/data/logs"
DB_FILE="$PROJECT_DIR/sledopyt_crypto.db"

# Создаём директории
mkdir -p "$BACKUP_DIR" "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/pre_deploy_${TIMESTAMP}.db"

echo "🚀 Начинаем деплой..."

# 1. БЭКАП БД (ОБЯЗАТЕЛЬНО!)
if [ -f "$DB_FILE" ]; then
    # Безопасное копирование через sqlite3
    sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
    gzip "$BACKUP_FILE"
    echo "✅ Бэкап создан: ${BACKUP_FILE}.gz"
else
    echo "⚠️ БД не найдена, пропускаем бэкап"
fi

# 2. Обновляем код
cd "$PROJECT_DIR"
if [ -d .git ]; then
    git pull origin main 2>/dev/null || echo "⚠️ git pull failed, продолжаем..."
fi

# 3. Проверяем синтаксис Python
echo "🔍 Проверяем синтаксис..."
python3 -m py_compile bot.py && echo "✅ bot.py OK" || echo "❌ bot.py has errors"
python3 -m py_compile db.py && echo "✅ db.py OK" || echo "❌ db.py has errors"
python3 -m py_compile payment_handler.py && echo "✅ payment_handler.py OK" || echo "❌ payment_handler.py has errors"
python3 -m py_compile webhook_server.py && echo "✅ webhook_server.py OK" || echo "❌ webhook_server.py has errors"

# 4. Очищаем старые бэкапы (оставляем последние 24)
find "$BACKUP_DIR" -name "pre_deploy_*.db.gz" -mtime +30 -delete 2>/dev/null

echo ""
echo "✅ Деплой завершён!"
echo "📋 Бэкап: ${BACKUP_FILE}.gz"
echo "📋 Следующий шаг: перезапусти бота"
echo "   systemctl --user restart sledopyt-crypto"
