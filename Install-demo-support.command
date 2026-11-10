#!/bin/zsh
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r server/requirements.txt
echo 'Demo support installed. Close the old helper and run Start-Mac.command again.'
read -k 1 '?Press a key to close.'
