#!/bin/bash
# 이 파일을 더블클릭하면 마리코가 켜집니다.
# 비밀번호 같은 개인 설정은 옆에 있는 .env 파일에서 읽어 옵니다.
#   (처음이라면:  cp 설정.env.예시 .env  하고 .env를 열어 채우세요)

cd "$(dirname "$0")" || exit 1

# 기본값 — .env 에 값이 있으면 그쪽이 이깁니다.
export MARIKO_ADD_DIR="$HOME/Desktop:$HOME/Documents"
export MARIKO_AUTOSAVE="commit"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# 서버가 도는 동안에는 맥이 저절로 잠들지 않게 한다.
# (전원이 연결돼 있을 때만. 노트북 덮개를 닫으면 이걸로도 못 막는다.)
if command -v caffeinate >/dev/null 2>&1; then
  exec caffeinate -i -s python3 server.py
else
  exec python3 server.py
fi
