#!/bin/zsh
cd -- "$(dirname -- "$0")/../.." || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print '이 폴더의 처음 설치.command를 먼저 한 번 실행하세요.'
  read -k 1
  exit 1
fi
.venv/bin/python Role04/scripts/launch_gui.py
if (( $? != 0 )); then
  print '\n실행에 실패했습니다. 위 오류를 확인하세요. 아무 키나 누르면 닫습니다.'
  read -k 1
fi
