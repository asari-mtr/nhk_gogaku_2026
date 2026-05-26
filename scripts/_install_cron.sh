#!/usr/bin/env bash
# cron 登録 (install.sh から呼ばれる内部スクリプト)
# 引数: PROJECT_ROOT PYTHON_BIN HOUR MINUTE
#
# 注意:
#   - cron は Mac/Linux 共通。実行時間に PC が起動・ログイン中である必要あり。
#   - DL ジョブのみ登録。HTTPサーバはバックグラウンド常駐用に @reboot で起動。
#
set -euo pipefail

PROJECT_ROOT="$1"; PYTHON_BIN="$2"; HOUR="$3"; MINUTE="$4"
MARKER_DL="# nhk-gogaku-2026-dl"
MARKER_SERVER="# nhk-gogaku-2026-server"

# 既存エントリを削除して書き戻す
TMPFILE=$(mktemp)
crontab -l 2>/dev/null | grep -v -F "$MARKER_DL" | grep -v -F "$MARKER_SERVER" > "$TMPFILE" || true

# DL: 毎日指定時刻
echo "$MINUTE $HOUR * * * cd $PROJECT_ROOT && $PYTHON_BIN nhk_dl.py >> $PROJECT_ROOT/logs/cron-dl.log 2>&1 $MARKER_DL" >> "$TMPFILE"

# サーバ: ログイン時に起動 (既に起動してたら何もしない)
echo "@reboot cd $PROJECT_ROOT && (pgrep -f 'serve.py' > /dev/null || nohup $PYTHON_BIN serve.py >> $PROJECT_ROOT/logs/cron-server.log 2>&1 &) $MARKER_SERVER" >> "$TMPFILE"

crontab "$TMPFILE"
rm -f "$TMPFILE"

echo "→ crontab に登録しました:"
crontab -l | grep -E "$MARKER_DL|$MARKER_SERVER" | sed 's/^/    /'

# サーバを今すぐ起動 (まだ起動してなければ)
if ! pgrep -f "$PROJECT_ROOT/serve.py" >/dev/null 2>&1; then
  echo "→ サーバを起動します"
  ( cd "$PROJECT_ROOT" && nohup "$PYTHON_BIN" serve.py >> "$PROJECT_ROOT/logs/cron-server.log" 2>&1 & )
  sleep 1
fi

echo
echo "⚠ cron の注意点:"
echo "  - PC がスリープ中 / シャットダウン中はジョブが走りません"
echo "  - macOSでDLを確実にしたい場合は launchd を推奨します"
