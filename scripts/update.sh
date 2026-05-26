#!/usr/bin/env bash
# NHK 語学ダウンローダ - アップデート
#
# やること:
#   1. git pull --ff-only で最新コードを取得
#   2. サーバを再起動 (launchd または cron で起動済みのものを対象)
#   3. config.json / series.json / downloads/ / state/ / feeds/ / logs/ は維持
#
# 使い方:
#   ./scripts/update.sh
#
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

LABEL_SERVER="local.nhk-gogaku-2026.server"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎙  NHK 語学ダウンローダ - アップデート"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  プロジェクト: $PROJECT_ROOT"
echo

# ─── git 確認 ───
if [[ ! -d ".git" ]]; then
  echo "✗ ここは git リポジトリではありません。bootstrap.sh で再インストールしてください。" >&2
  exit 1
fi

# ─── 未コミット変更チェック ───
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  echo "⚠ ローカルに未コミットの変更があります:"
  git status --short | sed 's/^/    /'
  echo
  read -r -p "それでも更新しますか？ (git pull --ff-only)  [y/N]: " ans
  if [[ ! "${ans:-N}" =~ ^[Yy] ]]; then
    echo "中断しました。"
    exit 0
  fi
fi

# ─── 更新 ───
BEFORE=$(git rev-parse --short HEAD 2>/dev/null || echo "?")
echo "→ 現在のバージョン: $BEFORE"
echo "→ git pull"
if ! git pull --ff-only; then
  echo "✗ pull に失敗しました。ブランチや競合を確認してください。" >&2
  exit 1
fi
AFTER=$(git rev-parse --short HEAD)
if [[ "$BEFORE" == "$AFTER" ]]; then
  echo "✓ 既に最新です ($AFTER)"
else
  echo "→ 新バージョン: $AFTER"
  # 変更内容のサマリ (簡易)
  echo
  echo "▶ 変更点 ($BEFORE..$AFTER):"
  git log --oneline "$BEFORE..$AFTER" | sed 's/^/    /' | head -20
  echo
fi

# ─── サーバ再起動 ───
restarted=0

# launchd 経由
if [[ "$(uname -s)" == "Darwin" ]] && launchctl print "gui/$(id -u)/$LABEL_SERVER" >/dev/null 2>&1; then
  echo "→ launchd サーバを再起動"
  launchctl kickstart -k "gui/$(id -u)/$LABEL_SERVER" && restarted=1
fi

# cron管理 (launchd で見つからなかった場合)
if [[ $restarted -eq 0 ]] && pgrep -f "$PROJECT_ROOT/serve.py" >/dev/null 2>&1; then
  echo "→ サーバプロセスを再起動 (cron/手動 管理)"
  pkill -f "$PROJECT_ROOT/serve.py" || true
  sleep 1
  PY=$(command -v python3 || echo "/opt/homebrew/bin/python3")
  ( cd "$PROJECT_ROOT" && nohup "$PY" serve.py >> "$PROJECT_ROOT/logs/server.out.log" 2>&1 & )
  restarted=1
fi

if [[ $restarted -eq 0 ]]; then
  echo "ℹ サーバは現在稼働していません (再起動はスキップ)"
fi

echo
echo "✓ 更新完了"

# ─── HTTPテスト ───
sleep 1
HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:8123/api/status" 2>&1 || echo "ERR")
if [[ "$code" == "200" ]]; then
  echo "  Web UI: http://${HOST}.local:8123/  (応答 OK)"
else
  echo "  Web UI 応答テスト: $code (サーバ未起動なら正常)"
fi
