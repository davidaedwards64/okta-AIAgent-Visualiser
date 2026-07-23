#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/backend"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -e ".[dev]"

exec uvicorn app.main:app --reload --port 8000
