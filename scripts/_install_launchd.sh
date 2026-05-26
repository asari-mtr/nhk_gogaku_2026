#!/usr/bin/env bash
# launchd エージェント登録 (install.sh から呼ばれる内部スクリプト)
# 引数: PROJECT_ROOT PYTHON_BIN USER_PATH HOUR MINUTE LABEL_DL LABEL_SERVER
set -euo pipefail

PROJECT_ROOT="$1"; PYTHON_BIN="$2"; USER_PATH="$3"
HOUR="$4"; MINUTE="$5"; LABEL_DL="$6"; LABEL_SERVER="$7"
LAUNCH_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LAUNCH_DIR"

# 既存をクリーンアップ
for label in "$LABEL_DL" "$LABEL_SERVER" \
             "com.mitsuteru.nhk-gogaku" "com.mitsuteru.nhk-server"; do
  if launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    echo "→ 既存 $label を停止"
    launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  fi
  rm -f "$LAUNCH_DIR/$label.plist"
done

cat > "$LAUNCH_DIR/$LABEL_DL.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL_DL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$PROJECT_ROOT/nhk_dl.py</string>
    </array>
    <key>WorkingDirectory</key><string>$PROJECT_ROOT</string>
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>$USER_PATH</string></dict>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>$HOUR</integer>
        <key>Minute</key><integer>$MINUTE</integer>
    </dict>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key><string>$PROJECT_ROOT/logs/launchd.out.log</string>
    <key>StandardErrorPath</key><string>$PROJECT_ROOT/logs/launchd.err.log</string>
</dict>
</plist>
EOF

cat > "$LAUNCH_DIR/$LABEL_SERVER.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL_SERVER</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON_BIN</string>
        <string>$PROJECT_ROOT/serve.py</string>
    </array>
    <key>WorkingDirectory</key><string>$PROJECT_ROOT</string>
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>$USER_PATH</string></dict>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$PROJECT_ROOT/logs/server.out.log</string>
    <key>StandardErrorPath</key><string>$PROJECT_ROOT/logs/server.err.log</string>
</dict>
</plist>
EOF

launchctl bootstrap "gui/$(id -u)" "$LAUNCH_DIR/$LABEL_DL.plist"
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_DIR/$LABEL_SERVER.plist"
echo "→ launchd に登録完了: $LABEL_DL / $LABEL_SERVER"
