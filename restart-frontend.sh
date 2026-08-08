#!/bin/zsh

set -e

PROJECT_DIR="/Users/cuc2023/Documents/Codex/2026-06-23/codex-codex"
PORT=4173

PID="$(lsof -tiTCP:${PORT} -sTCP:LISTEN 2>/dev/null || true)"
if [[ -n "$PID" ]]; then
  kill "$PID"
  sleep 1
fi

cd "$PROJECT_DIR"
exec node frontend/server.mjs
