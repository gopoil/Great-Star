#!/bin/bash
# 이 파일을 더블클릭하면 마리코가 켜집니다.
# 설정을 바꾸려면 이 파일을 텍스트 편집기로 열어 아래 두 줄만 고치세요.

cd "$(dirname "$0")" || exit 1

# 마리코가 읽고 쓸 수 있는 폴더. 콜론(:)으로 나눠 적습니다.
# 옵시디언 볼트가 다른 곳에 있으면 그 경로를 뒤에 붙이세요.
#   예: "$HOME/Desktop:$HOME/Documents:$HOME/Obsidian볼트"
export MARIKO_ADD_DIR="$HOME/Desktop:$HOME/Documents"

# 대화가 끝날 때마다 마리코/ 폴더를 git에 기록합니다. 끄려면 이 줄을 지우세요.
export MARIKO_AUTOSAVE=commit

exec python3 server.py
