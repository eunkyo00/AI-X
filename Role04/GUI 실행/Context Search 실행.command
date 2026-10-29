#!/bin/zsh
cd -- "$(dirname -- "$0")/.." || exit 1
if [[ -x ../.venv/bin/python ]]; then
  ../.venv/bin/python scripts/serve_web.py --open-browser
elif command -v python3 >/dev/null 2>&1; then
  python3 scripts/serve_web.py --open-browser
else
  print 'Python과 검색 패키지를 설치하세요. Role04/README.md를 참고하세요.'
  read -k 1
  exit 1
fi
