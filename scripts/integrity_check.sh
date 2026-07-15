#!/bin/bash
# scripts/integrity_check.sh — Проверка целостности БД
# crontab: 0 3 * * * /home/dima/sledopyt-crypto-v2/scripts/integrity_check.sh

DB_FILE="/home/dima/sledopyt-crypto-v2/sledopyt_crypto.db"
LOG_FILE="/home/dima/sledopyt-crypto-v2/data/logs/integrity.log"

mkdir -p "$(dirname $LOG_FILE)"

RESULT=$(sqlite3 "$DB_FILE" "PRAGMA integrity_check;" 2>&1)

if [ "$RESULT" = "ok" ]; then
    echo "[$(date)] OK" >> "$LOG_FILE"
else
    echo "[$(date)] ERROR: $RESULT" >> "$LOG_FILE"
    echo "🚨 CRITICAL: БД повреждена! Проверь логи: $LOG_FILE"
fi
