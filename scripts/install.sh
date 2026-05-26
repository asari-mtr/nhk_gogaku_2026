#!/usr/bin/env bash
# NHK 語学ダウンローダ - 対話型インストール
#
# 機能:
#   - OS自動判定 (macOS / Linux)
#   - スケジューラ選択 (launchd / cron / なし)
#   - 実行時刻、保存形式 (m4a/mp3)、ビットレートを対話で設定
#   - config.json と LaunchAgents/crontab を生成
#
# 非対話モード:
#   ./scripts/install.sh --non-interactive --scheduler launchd \
#     --hour 9 --minute 0 --format m4a [--mp3-bitrate 128k]
#
set -euo pipefail

# ─── デフォルト ───
LABEL_DL="local.nhk-gogaku-2026.dl"
LABEL_SERVER="local.nhk-gogaku-2026.server"
HOUR=9
MINUTE=0
FORMAT="m4a"
MP3_BITRATE="128k"
SCHEDULER=""
NON_INTERACTIVE=0

# ─── 引数 ───
while [[ $# -gt 0 ]]; do
  case "$1" in
    --non-interactive) NON_INTERACTIVE=1; shift ;;
    --scheduler) SCHEDULER="$2"; shift 2 ;;
    --hour) HOUR="$2"; shift 2 ;;
    --minute) MINUTE="$2"; shift 2 ;;
    --format) FORMAT="$2"; shift 2 ;;
    --mp3-bitrate) MP3_BITRATE="$2"; shift 2 ;;
    -h|--help)
      grep "^#" "$0" | sed 's/^# \{0,1\}//' | head -15
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

# ─── パス解決 ───
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "Error: python3 が見つかりません" >&2
  exit 1
fi
USER_PATH="$(dirname "$PYTHON_BIN"):/usr/local/bin:/usr/bin:/bin"
OS_TYPE=$(uname -s)

# ─── OS推奨スケジューラ ───
case "$OS_TYPE" in
  Darwin) DEFAULT_SCHEDULER="launchd" ;;
  Linux)  DEFAULT_SCHEDULER="cron" ;;
  *)      DEFAULT_SCHEDULER="cron" ;;
esac

# ─── ヘルパ: 対話プロンプト ───
ask() {
  local prompt="$1" default="$2" var
  read -r -p "$prompt [$default]: " var
  echo "${var:-$default}"
}

ask_choice() {
  # ask_choice "質問" デフォルト番号 "選択肢1" "選択肢2" ...
  local prompt="$1" default="$2"; shift 2
  local i=1
  for opt in "$@"; do
    if [[ $i -eq $default ]]; then
      echo "  $i) $opt  ★recommend" >&2
    else
      echo "  $i) $opt" >&2
    fi
    i=$((i + 1))
  done
  local choice
  read -r -p "選択 [$default]: " choice
  choice="${choice:-$default}"
  if ! [[ "$choice" =~ ^[0-9]+$ ]] || [[ "$choice" -lt 1 ]] || [[ "$choice" -gt $# ]]; then
    echo "Invalid choice" >&2
    exit 1
  fi
  echo "$choice"
}

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🎙  NHK 語学ダウンローダ - セットアップ"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  プロジェクト: $PROJECT_ROOT"
echo "  Python:       $PYTHON_BIN"
echo "  OS:           $OS_TYPE"
echo "  推奨:         $DEFAULT_SCHEDULER"
echo

# ─── 対話モード ───
if [[ $NON_INTERACTIVE -eq 0 ]]; then
  # スケジューラ
  echo "▶ スケジューラを選んでください"
  if [[ "$DEFAULT_SCHEDULER" == "launchd" ]]; then
    echo "  (macOSではlaunchdが推奨: スリープ復帰後に追いかけ実行されます)"
    n=$(ask_choice "" 1 "launchd (推奨)" "cron" "登録しない")
    case "$n" in
      1) SCHEDULER="launchd" ;;
      2) SCHEDULER="cron" ;;
      3) SCHEDULER="none" ;;
    esac
  else
    echo "  (Linuxではcronが標準)"
    n=$(ask_choice "" 1 "cron (推奨)" "登録しない")
    case "$n" in
      1) SCHEDULER="cron" ;;
      2) SCHEDULER="none" ;;
    esac
  fi
  echo

  # 時刻
  if [[ "$SCHEDULER" != "none" ]]; then
    echo "▶ DL実行時刻 (HH:MM)"
    TIME=$(ask "  時刻" "$(printf '%02d:%02d' "$HOUR" "$MINUTE")")
    if [[ "$TIME" =~ ^([0-9]{1,2}):([0-9]{1,2})$ ]]; then
      HOUR=$((10#${BASH_REMATCH[1]}))
      MINUTE=$((10#${BASH_REMATCH[2]}))
    else
      echo "Invalid time format" >&2; exit 1
    fi
    echo
  fi

  # フォーマット
  echo "▶ 保存形式を選んでください"
  echo "  (m4a = 元配信そのまま、無劣化、約1.7MB/5分。"
  echo "   mp3 = 再エンコード、互換性高い、軽い劣化)"
  n=$(ask_choice "" 1 "m4a (推奨: Apple/主要Podcastアプリ向け)" "mp3 (Spotify/Android/古い機器向け)")
  case "$n" in
    1) FORMAT="m4a" ;;
    2) FORMAT="mp3"
       echo
       echo "▶ mp3 ビットレート"
       n2=$(ask_choice "" 2 "64 kbps (小容量、語学十分)" "128 kbps (推奨)" "192 kbps (高音質)")
       case "$n2" in
         1) MP3_BITRATE="64k" ;;
         2) MP3_BITRATE="128k" ;;
         3) MP3_BITRATE="192k" ;;
       esac
       ;;
  esac
  echo

  # 確認
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  以下の内容でセットアップします:"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  スケジューラ:  $SCHEDULER"
  [[ "$SCHEDULER" != "none" ]] && echo "  DL実行時刻:    $(printf '%02d:%02d' "$HOUR" "$MINUTE")"
  echo "  保存形式:      $FORMAT$([[ $FORMAT == mp3 ]] && echo " ($MP3_BITRATE)")"
  echo
  ans=$(ask "続行しますか？ [y/N]" "y")
  if [[ ! "$ans" =~ ^[Yy] ]]; then
    echo "中断しました"; exit 0
  fi
fi

# ─── デフォルト適用 (非対話) ───
[[ -z "$SCHEDULER" ]] && SCHEDULER="$DEFAULT_SCHEDULER"

# ─── config.json 生成 ───
cat > "$PROJECT_ROOT/config.json" <<EOF
{
  "format": "$FORMAT",
  "mp3_bitrate": "$MP3_BITRATE",
  "schedule": {
    "type": "$SCHEDULER",
    "hour": $HOUR,
    "minute": $MINUTE
  }
}
EOF
echo "✓ config.json を生成しました"

mkdir -p "$PROJECT_ROOT/logs"

# ─── スケジューラ登録 ───
case "$SCHEDULER" in
  launchd)
    "$(dirname "$0")/_install_launchd.sh" \
      "$PROJECT_ROOT" "$PYTHON_BIN" "$USER_PATH" "$HOUR" "$MINUTE" \
      "$LABEL_DL" "$LABEL_SERVER"
    ;;
  cron)
    "$(dirname "$0")/_install_cron.sh" \
      "$PROJECT_ROOT" "$PYTHON_BIN" "$HOUR" "$MINUTE"
    ;;
  none)
    echo "→ スケジューラ登録はスキップしました"
    echo "  手動実行: cd $PROJECT_ROOT && python3 nhk_dl.py"
    ;;
esac

echo
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ セットアップ完了"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [[ "$SCHEDULER" == "launchd" ]]; then
  HOST=$(scutil --get LocalHostName 2>/dev/null || hostname -s)
  echo "  Web UI: http://${HOST}.local:8123/  または  http://${HOST}:8123/"
  echo "  状態確認: ./scripts/status.sh"
  echo "  アンインストール: ./scripts/uninstall.sh"
elif [[ "$SCHEDULER" == "cron" ]]; then
  echo "  crontab 確認: crontab -l | grep nhk-gogaku-2026"
  echo "  状態確認: ./scripts/status.sh"
  echo "  アンインストール: ./scripts/uninstall.sh"
fi
