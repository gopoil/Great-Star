#!/bin/bash
# 돌고 있던 마리코를 끄고 새로 켭니다.
# .env 를 고친 뒤나, "자리를 이미 누가 쓰고 있습니다" 가 뜰 때 쓰세요.

cd "$(dirname "$0")" || exit 1

PORT=8765
if [ -f .env ]; then
  FROM_ENV="$(grep -m1 '^MARIKO_PORT=' .env | cut -d= -f2- | tr -d '[:space:]')"
  [ -n "$FROM_ENV" ] && PORT="$FROM_ENV"
fi

holders() { lsof -ti "tcp:$PORT" 2>/dev/null; }

PIDS="$(holders)"
if [ -n "$PIDS" ]; then
  echo "  $PORT번을 쓰고 있던 마리코를 끕니다."
  # shellcheck disable=SC2086
  kill $PIDS 2>/dev/null
  for _ in 1 2 3 4 5; do
    sleep 1
    [ -z "$(holders)" ] && break
  done
  PIDS="$(holders)"
  if [ -n "$PIDS" ]; then
    echo "  말을 안 들어서 강제로 끕니다."
    # shellcheck disable=SC2086
    kill -9 $PIDS 2>/dev/null
    sleep 1
  fi
fi

echo
exec bash 켜기.command
