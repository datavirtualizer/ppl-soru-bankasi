#!/usr/bin/env bash
# Geliştirme sunucusu.  Üretim için server/README.md'ye bak.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
exec .venv/bin/uvicorn app:app --app-dir server --host 127.0.0.1 --port 8778 --reload
