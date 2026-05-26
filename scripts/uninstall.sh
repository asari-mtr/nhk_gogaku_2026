#!/usr/bin/env bash
# launchd / cron 両方からアンインストール
set -euo pipefail

LABEL_DL="local.nhk-gogaku-2026.dl"
LABEL_SERVER="local.nhk-gogaku-2026.server"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
MARKER_DL="# nhk-gogaku-2026-dl"
MARKER_SERVER="# nhk-gogaku-2026-server"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  NHK 語学ダウンローダ - アンインストール"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── launchd ───
if [[ "$(uname -s)" == "Darwin" ]]; then
  for label in "$LABEL_DL" "$LABEL_SERVER"; do
    if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
      echo "→ launchd $label を停止"
      launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
    fi
    if [[ -f "$LAUNCH_DIR/$label.plist" ]]; then
      echo "→ $LAUNCH_DIR/$label.plist を削除"
      rm -f "$LAUNCH_DIR/$label.plist"
    fi
  done
fi

# ─── cron ───
if crontab -l 2>/dev/null | grep -qE "$MARKER_DL|$MARKER_SERVER"; then
  echo "→ crontab から該当エントリを削除"
  TMPFILE=$(mktemp)
  crontab -l 2>/dev/null | grep -v -F "$MARKER_DL" | grep -v -F "$MARKER_SERVER" > "$TMPFILE" || true
  if [[ -s "$TMPFILE" ]]; then
    crontab "$TMPFILE"
  else
    crontab -r 2>/dev/null || true
  fi
  rm -f "$TMPFILE"
fi

# ─── 起動中のサーバプロセスを停止 (cron で立てた分) ───
if pgrep -f "$PROJECT_ROOT/serve.py" >/dev/null 2>&1; then
  echo "→ サーバプロセスを停止"
  pkill -f "$PROJECT_ROOT/serve.py" || true
fi

echo
echo "✓ アンインストール完了"
echo
echo "DL済ファイル / 設定 / ログは残しています:"
echo "  - $PROJECT_ROOT/downloads"
echo "  - $PROJECT_ROOT/feeds"
echo "  - $PROJECT_ROOT/state"
echo "  - $PROJECT_ROOT/logs"
echo "  - $PROJECT_ROOT/config.json"
echo "完全に消す場合は手動で削除してください。"
