#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HOST=127.0.0.1 PUBLIC_MODE=false ALLOWED_HOSTS='localhost,127.0.0.1,[::1]'
if [ ! -x .venv/bin/python ]; then printf '%s\n' 'Run bash scripts/setup.sh first.' >&2; exit 1; fi
exec .venv/bin/python backend/main.py
