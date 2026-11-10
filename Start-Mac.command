#!/bin/zsh
cd "$(dirname "$0")" || exit 1
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python -m server.scout --open
else
  python3 -m server.scout --open
fi
read -k 1 '?Press a key to close.'
