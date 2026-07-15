#!/bin/bash
# scripts/backup.sh — Автобэкап БД каждые 6 часов
# crontab: 0 */6 * * * /home/dima/sledopyt-crypto-v2/scripts/backup.sh

set -e

PROJECT_DIR="/home/dima/sledopyt-crypto-v2"
BACKUP_DIR="$PROJECT_DIR/data/backups"
DB_FILE="$PROJECT_DIR/sledopyt_crypto.db"
LOG_FILE="$PROJECT_DIR/data/logs/backups.log"

mkdir -p "$BACKUP_DIR" "$(dirname $LOG_FILE)"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/db_${TIMESTAMP}.db"

if [ ! -f "$DB_FILE" ]; then
    echo "[$(date)] ERROR: БД не найдена: $DB_FILE" >> "$LOG_FILE"
    exit 1
fi

# Безопасное копирование
sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"

# Сжимаем
gzip "$BACKUP_FILE"

# Логируем
echo "[$(date)] Backup created: ${BACKUP_FILE}.gz ($(du -h ${BACKUP_FILE}.gz | cut -f1))" >> "$LOG_FILE"

# Очистка:
# - последние 24 часа (6 файлов)
# - по 1 в день за последние 7 дней
# - по 1 в неделю за последний месяц
find "$BACKUP_DIR" -name "db_*.db.gz" -mtime +30 -delete 2>/dev/null

echo "✅ Backup done: ${BACKUP_FILE}.gz"
