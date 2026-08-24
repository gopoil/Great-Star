#!/bin/bash
# 더블클릭하면 "맥에 로그인할 때 마리코가 저절로 켜지도록" 등록합니다.
# 끄고 싶으면 옆에 있는 자동실행_해제.command 를 더블클릭하세요.

set -e
cd "$(dirname "$0")"
HERE="$(pwd)"
LABEL="com.mariko.chat"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -f "$HERE/server.py" ]; then
  echo "server.py 를 찾을 수 없습니다. 이 파일이 Great-Star 폴더 안에 있는지 확인해 주세요."
  read -r -p "엔터를 누르면 닫힙니다." _
  exit 1
fi

chmod +x "$HERE/켜기.command"
mkdir -p "$HOME/Library/LaunchAgents"

# 이미 등록돼 있으면 먼저 내린다.
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$HERE/켜기.command</string>
  </array>

  <key>WorkingDirectory</key>
  <string>$HERE</string>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <true/>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>

  <key>StandardOutPath</key>
  <string>$HERE/마리코.log</string>
  <key>StandardErrorPath</key>
  <string>$HERE/마리코.log</string>
</dict>
</plist>
PLISTEOF

launchctl bootstrap "gui/$UID" "$PLIST"

echo
echo "  등록했습니다. 이제 맥에 로그인하면 마리코가 저절로 켜집니다."
echo "  지금도 켜졌습니다:  http://localhost:8765"
echo
echo "  뭔가 이상하면 이 폴더의 '마리코.log' 파일을 열어 보세요."
echo "  끄려면 '자동실행_해제.command' 를 더블클릭하세요."
echo
read -r -p "엔터를 누르면 닫힙니다." _
