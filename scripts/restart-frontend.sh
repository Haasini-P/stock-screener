#!/bin/bash
# Restarts the Next.js dev server (next dev on :3000). Spawned detached by
# POST /api/system/restart so it outlives the backend request that triggered it.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/frontend.log"

PIDS=$(lsof -ti:3000 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
  for i in 1 2 3 4 5; do
    lsof -ti:3000 -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 1
  done
  lsof -ti:3000 -sTCP:LISTEN 2>/dev/null | xargs -r kill -9 2>/dev/null || true
fi

cd "$ROOT/frontend"
echo "=== restart $(date) ===" >> "$LOG"
nohup npm run dev >> "$LOG" 2>&1 &
disown
