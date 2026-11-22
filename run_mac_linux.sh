#!/usr/bin/env bash
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt
(sleep 2; command -v open >/dev/null && open http://localhost:8000 || command -v xdg-open >/dev/null && xdg-open http://localhost:8000) &
python app.py
