#!/bin/bash
# Deploy с автоматическим rollback
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$(dirname "$DIR")"
SVC="crypto-scout"
LOG="$PROJECT/logs/deploys.log"
BRANCH="${1:-main}"

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

log "=== Deploy started (branch: $BRANCH) ==="

cd "$PROJECT"

# 1. Backup
"$DIR/backup.sh"
LATEST=$(ls -t data/backups/db_*.db.gz | head -1)
CURRENT=$(git rev-parse HEAD)

# 2. Pull
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"
NEW=$(git rev-parse HEAD)

# 3. Deps
if ! git diff "$CURRENT" "$NEW" --quiet requirements.txt 2>/dev/null; then
    pip install -r requirements.txt --quiet 2>/dev/null || true
fi

# 4. Restart
if systemctl is-active --quiet "$SVC" 2>/dev/null; then
    sudo systemctl restart "$SVC"
    sleep 5
    if ! systemctl is-active --quiet "$SVC"; then
        log "ERROR: Service failed! Rolling back..."
        git reset --hard "$CURRENT"
        gunzip -c "$LATEST" > data/bot.db 2>/dev/null
        sudo systemctl restart "$SVC"
        log "Rollback done"
        exit 1
    fi
fi

log "=== Deploy OK: $CURRENT -> $NEW ==="
