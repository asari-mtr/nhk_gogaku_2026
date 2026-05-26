#!/usr/bin/env bash
# launchd / cron 両方の状態を確認
set -euo pipefail

LABEL_DL="local.nhk-gogaku-2026.dl"
LABEL_SERVER="local.nhk-gogaku-2026.server"
MARKER_DL="# nhk-gogaku-2026-dl"
MARKER_SERVER="# nhk-gogaku-2026-server"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NHK 語学ダウンローダ - 状態確認"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# config.json
if [[ -f "$PROJECT_ROOT/config.json" ]]; then
  echo
  echo "▶ 設定 (config.json):"
  sed 's/^/    /' "$PROJECT_ROOT/config.json"
fi

# launchd
if [[ "$(uname -s)" == "Darwin" ]]; then
  for label in "$LABEL_DL" "$LABEL_SERVER"; do
    echo
    echo "▶ launchd: $label"
    if launchctl print "gui/$(id -u)/$label" 2>/dev/null \
       | grep -E "state|pid|last exit code" | head -3 | sed 's/^/    /'; then
      :
    else
      echo "    (未登録)"
    fi
  done
fi

# cron
echo
echo "▶ cron:"
if crontab -l 2>/dev/null | grep -E "$MARKER_DL|$MARKER_SERVER" | sed 's/^/    /'; then
  :
else
  echo "    (未登録)"
fi

# サーバプロセス
echo
echo "▶ サーバプロセス:"
pids=$(pgrep -f "$PROJECT_ROOT/serve.py" 2>/dev/null || true)
if [[ -n "$pids" ]]; then
  echo "    PID: $pids"
else
  echo "    (起動していません)"
fi

# HTTP応答
echo
echo "▶ HTTP応答:"
HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
for url in "http://localhost:8123/api/status" "http://${HOST}.local:8123/api/status"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>&1 || echo "ERR")
  echo "    $url → $code"
done
