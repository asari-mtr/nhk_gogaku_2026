#!/usr/bin/env bash
# NHK 語学ダウンローダ - ワンライナーインストーラ
#
# 使い方 (ターミナルにこれだけ貼り付け):
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/asari-mtr/nhk_gogaku_2026/main/bootstrap.sh)"
#
# やること:
#   1. macOS / Linux を判定 (Windowsは WSL を案内)
#   2. 依存ツール (git / curl / python3 / ffmpeg / uv) を **確認**
#      → 不足していたら、OS に応じたインストールコマンドを表示して終了
#      (勝手に sudo / brew install などはしない)
#   3. プロジェクトを ~/nhk_gogaku_2026 に git clone
#   4. 対話型セットアップ (scripts/install.sh) を起動
#
# 環境変数:
#   NHK_GOGAKU_DIR  ... 配置先 (デフォルト: $HOME/nhk_gogaku_2026)
#   NHK_REPO_URL    ... 別のレポからインストール
#   NHK_REPO_BRANCH ... 別ブランチ (デフォルト: main)
#
set -euo pipefail

# ─── 色 ───
if [[ -t 1 ]]; then
  C_BOLD=$'\033[1m'; C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_RESET=$'\033[0m'
else
  C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_RESET=""
fi
info() { echo "${C_GREEN}→${C_RESET} $*"; }
warn() { echo "${C_YELLOW}⚠${C_RESET} $*"; }
err()  { echo "${C_RED}✗${C_RESET} $*" >&2; }

# ─── 設定 ───
REPO_URL="${NHK_REPO_URL:-https://github.com/asari-mtr/nhk_gogaku_2026.git}"
REPO_BRANCH="${NHK_REPO_BRANCH:-main}"
INSTALL_DIR="${NHK_GOGAKU_DIR:-$HOME/nhk_gogaku_2026}"

cat <<EOF
${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}
${C_BOLD}  🎙  NHK 語学ダウンローダ - ブートストラップ${C_RESET}
${C_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${C_RESET}
  リポジトリ:  $REPO_URL ($REPO_BRANCH)
  配置先:      $INSTALL_DIR
EOF
echo

# ─── OS判定 ───
OS_TYPE=$(uname -s)
case "$OS_TYPE" in
  Darwin)
    info "macOS を検出"
    OS_LABEL="macos"
    ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null; then
      info "WSL (Linux on Windows) を検出"
    else
      info "Linux を検出"
    fi
    # distro判定
    if [[ -f /etc/os-release ]]; then
      # shellcheck disable=SC1091
      . /etc/os-release
      case "${ID:-}${ID_LIKE:-}" in
        *debian*|*ubuntu*) OS_LABEL="debian" ;;
        *fedora*|*rhel*|*centos*) OS_LABEL="fedora" ;;
        *arch*|*manjaro*) OS_LABEL="arch" ;;
        *suse*) OS_LABEL="suse" ;;
        *) OS_LABEL="linux" ;;
      esac
    else
      OS_LABEL="linux"
    fi
    ;;
  MINGW*|MSYS*|CYGWIN*)
    err "Windowsネイティブでは動きません。WSL (Windows Subsystem for Linux) を使ってください。"
    cat <<'EOF'

  PowerShell (管理者) で:
    wsl --install -d Ubuntu

  Ubuntu起動後、その中でもう一度このコマンドを実行してください。
EOF
    exit 1 ;;
  *)
    err "未対応OS: $OS_TYPE"
    exit 1 ;;
esac

# ─── 依存チェックヘルパ ───
# 各OS向けに「論理パッケージ → 実際のインストールコマンド」を返す
hint_install() {
  local pkg="$1"
  case "$OS_LABEL" in
    macos)
      if [[ "$pkg" == "uv" ]]; then
        echo "brew install uv   # または公式: curl -LsSf https://astral.sh/uv/install.sh | sh"
      elif [[ "$pkg" == "python3" ]]; then
        echo "brew install python"
      else
        echo "brew install $pkg"
      fi ;;
    debian)
      case "$pkg" in
        uv)      echo "curl -LsSf https://astral.sh/uv/install.sh | sh   # apt にはありません" ;;
        python3) echo "sudo apt update && sudo apt install -y python3 python3-pip" ;;
        *)       echo "sudo apt update && sudo apt install -y $pkg" ;;
      esac ;;
    fedora)
      case "$pkg" in
        uv)      echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        *)       echo "sudo dnf install -y $pkg" ;;
      esac ;;
    arch)
      case "$pkg" in
        uv)      echo "sudo pacman -S uv   # または: curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        python3) echo "sudo pacman -S python" ;;
        *)       echo "sudo pacman -S $pkg" ;;
      esac ;;
    suse)
      case "$pkg" in
        uv) echo "curl -LsSf https://astral.sh/uv/install.sh | sh" ;;
        *)  echo "sudo zypper install -y $pkg" ;;
      esac ;;
    *)
      echo "(該当OSの方法で $pkg をインストール)" ;;
  esac
}

# ─── 必須/任意の依存確認 ───
MISSING_REQUIRED=()
MISSING_OPTIONAL=()

for cmd in git curl python3 ffmpeg; do
  command -v "$cmd" >/dev/null 2>&1 || MISSING_REQUIRED+=("$cmd")
done
# uv は任意 (manage_series.py 専用)
command -v uv >/dev/null 2>&1 || MISSING_OPTIONAL+=("uv")

# macOSの場合は brew も必須前提として案内 (パッケージマネージャがない macOS は厳しい)
if [[ "$OS_LABEL" == "macos" ]] && ! command -v brew >/dev/null 2>&1; then
  err "Homebrew がありません。先にこちらをインストールしてください:"
  cat <<'EOF'

  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

EOF
  exit 1
fi

# ─── 不足がある場合: コマンドを表示して終了 ───
if [[ ${#MISSING_REQUIRED[@]} -gt 0 ]]; then
  warn "以下のコマンドが不足しています:"
  echo
  for pkg in "${MISSING_REQUIRED[@]}"; do
    echo "  ${C_BOLD}・$pkg${C_RESET}"
    echo "      $(hint_install "$pkg")"
  done
  echo
  err "これらを手動でインストールしてから、もう一度このコマンドを実行してください。"
  exit 1
fi
info "必須依存OK (git / curl / python3 / ffmpeg)"

# ─── uv (任意) のチェック ───
if [[ ${#MISSING_OPTIONAL[@]} -gt 0 ]]; then
  warn "任意ツールが不足しています:"
  for pkg in "${MISSING_OPTIONAL[@]}"; do
    echo "  ${C_BOLD}・$pkg${C_RESET} (CLI で番組選択する manage_series.py 用)"
    echo "      $(hint_install "$pkg")"
  done
  warn "→ Web UI から番組設定する場合は不要です。このまま続行します。"
  echo
fi

# ─── clone or pull ───
if [[ -d "$INSTALL_DIR/.git" ]]; then
  info "$INSTALL_DIR を最新化"
  git -C "$INSTALL_DIR" pull --ff-only origin "$REPO_BRANCH" || \
    warn "pull に失敗 (ローカル変更があるかも)"
else
  if [[ -d "$INSTALL_DIR" ]]; then
    err "$INSTALL_DIR が既に存在 (gitリポジトリではない)"
    err "別の場所にしたい場合: NHK_GOGAKU_DIR=/別パス を指定して再実行"
    exit 1
  fi
  info "$INSTALL_DIR に clone"
  git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

# ─── 対話セットアップ ───
echo
info "対話セットアップを開始します"
echo
exec "$INSTALL_DIR/scripts/install.sh"
