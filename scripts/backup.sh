#!/bin/bash
# Автобэкап SQLite БД (cron: 0 */6 * * *)
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$DIR")"
DB="$PROJECT/data/bot.db"
BACKUP_DIR="$PROJECT/data/backups"
LOG="$PROJECT/logs/backups.log"
TS=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR" "$(dirname "$LOG")"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

if [ ! -f "$DB" ]; then log "ERROR: DB not found"; exit 1; fi

INTEGRITY=$(sqlite3 "$DB" "PRAGMA integrity_check" 2>&1)
if [ "$INTEGRITY" != "ok" ]; then log "ERROR: DB corrupted: $INTEGRITY"; exit 1; fi

sqlite3 "$DB" ".backup '$BACKUP_DIR/db_$TS.db'"
gzip "$BACKUP_DIR/db_$TS.db"
SIZE=$(du -h "$BACKUP_DIR/db_$TS.db.gz" | cut -f1)
log "Backup OK: db_$TS.db.gz ($SIZE)"

# Retention: 30 дней
find "$BACKUP_DIR" -name "db_*.db.gz" -mtime +30 -delete 2>/dev/null
COUNT=$(find "$BACKUP_DIR" -name "db_*.db.gz" | wc -l)
log "Total backups: $COUNT"
