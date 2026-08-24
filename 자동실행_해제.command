#!/bin/bash
# 더블클릭하면 자동 실행을 끕니다. 마리코 자체가 지워지는 건 아닙니다.

LABEL="com.mariko.chat"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
rm -f "$PLIST"

echo
echo "  자동 실행을 껐습니다."
echo "  앞으로는 '켜기.command' 를 더블클릭해서 직접 켜시면 됩니다."
echo
read -r -p "엔터를 누르면 닫힙니다." _
