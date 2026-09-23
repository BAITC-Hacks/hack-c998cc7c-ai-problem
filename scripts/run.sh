#!/usr/bin/env bash
# Хаттама AI — запуск сервера (FastAPI + веб-интерфейс)
set -euo pipefail
cd "$(dirname "$0")/.."

[ -d .venv ] || { echo "Сначала выполните: bash scripts/setup.sh"; exit 1; }
. .venv/bin/activate

# Загружаем настройки из .env (если есть)
set -a
[ -f .env ] && . ./.env
set +a

echo "==> Хаттама AI — автопротоколирование совещаний"
echo "    http://localhost:${PORT:-8000}"
export PYTHONPATH="$PWD/backend:${PYTHONPATH:-}"
exec uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"