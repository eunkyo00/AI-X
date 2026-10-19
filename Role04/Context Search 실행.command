#!/bin/zsh
cd -- "$(dirname -- "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  python3 scripts/serve_web.py --open-browser
else
  print 'Python 3.10 이상을 설치한 뒤 다시 실행하세요. Role04/README.md를 참고하세요.'
  read -k 1
  exit 1
fi
