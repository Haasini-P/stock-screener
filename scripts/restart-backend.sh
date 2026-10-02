#!/bin/bash
# Restarts the FastAPI dev server (uvicorn --reload on :8000).
#
# Spawned detached by POST /api/system/restart, which runs inside the very
# process this script kills — so the short sleep up front isn't cosmetic,
# it's what lets the HTTP response reach the browser before the kill.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
mkdir -p "$ROOT/logs"
LOG="$ROOT/logs/backend.log"

sleep 1

PIDS=$(lsof -ti:8000 -sTCP:LISTEN 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  kill $PIDS 2>/dev/null || true
  for i in 1 2 3 4 5; do
    lsof -ti:8000 -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 1
  done
  lsof -ti:8000 -sTCP:LISTEN 2>/dev/null | xargs -r kill -9 2>/dev/null || true
fi

cd "$ROOT/backend"
echo "=== restart $(date) ===" >> "$LOG"
nohup .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload >> "$LOG" 2>&1 &
disown
