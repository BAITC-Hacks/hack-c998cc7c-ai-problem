#!/usr/bin/env bash
# Хаттама AI — установка окружения для on-premise / локального запуска
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Определяем Python (нужен 3.10+)"
PY=""
for cand in python3.11 python3.12 python3.13 python3; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    if "$cand" -c 'import venv, ensurepip' 2>/dev/null; then PY="$cand"; break; fi
  fi
done
[ -n "$PY" ] || { echo "Нет Python 3.10+ с модулем venv. Установите: apt install python3.11-venv"; exit 1; }
echo "    используем: $PY"

if [ ! -d .venv ]; then
  echo "==> Создаём виртуальное окружение .venv"
  "$PY" -m venv .venv
fi
. .venv/bin/activate

echo "==> Устанавливаем зависимости"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> Предзагружаем модель распознавания речи ($(grep -q 'WHISPER_MODEL=' .env && grep 'WHISPER_MODEL=' .env | cut -d= -f2 || echo small))"
WHISPER_MODEL="$(sed -n 's/^WHISPER_MODEL=//p' .env | tail -1)"
PYTHONPATH=backend python - <<PY
from faster_whisper import WhisperModel
m = WhisperModel("${WHISPER_MODEL:-small}", device="cpu", compute_type="int8")
print("    модель готова:", type(m).__name__)
PY

echo "==> Проверка шрифтов для PDF (кириллица)"
FONT="$(find /usr/share/fonts -iname 'DejaVuSans*.ttf' 2>/dev/null | head -1)"
[ -n "$FONT" ] && echo "    найден: $FONT" || echo "    не найден — PDF может не показать кириллицу (см. README)"

echo ""
echo "✅ Готово. Запуск:  bash scripts/run.sh  →  http://localhost:8000"