#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
if [ ! -f backend/.env ]; then cp backend/.env.example backend/.env; fi
printf '%s\n' 'Models are separate: .venv/bin/python scripts/download_model.py --model small'
