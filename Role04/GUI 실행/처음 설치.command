#!/bin/zsh
cd -- "$(dirname -- "$0")/../.." || exit 1
if [[ ! -x .venv/bin/python ]]; then
  if command -v python3.13 >/dev/null 2>&1; then
    python3.13 -m venv .venv || exit 1
  else
    print 'Python 3.13을 먼저 설치하세요: https://www.python.org/downloads/'
    read -k 1
    exit 1
  fi
fi
.venv/bin/python -m pip install -r Role04/requirements-search.txt &&
.venv/bin/python Role04/scripts/prepare_search.py &&
.venv/bin/python Role04/scripts/launch_gui.py
if (( $? != 0 )); then
  print '\n설치 또는 실행 오류입니다. 위 오류를 확인하세요. 아무 키나 누르면 닫습니다.'
  read -k 1
fi
