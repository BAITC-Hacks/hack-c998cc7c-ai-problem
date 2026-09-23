#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export HOST=127.0.0.1 PUBLIC_MODE=false ALLOWED_HOSTS='localhost,127.0.0.1,[::1]'
exec .venv/bin/python backend/main.py
