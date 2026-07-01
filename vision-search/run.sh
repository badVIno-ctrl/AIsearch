#!/usr/bin/env bash
# ============================================================
#  Vision Search — запуск на macOS / Linux одной командой.
#  Скрипт сам создаёт виртуальное окружение и ставит зависимости.
#  Нужен только установленный Python 3.9+.
#      Запуск:  ./run.sh      (первый раз: chmod +x run.sh)
# ============================================================
set -e
cd "$(dirname "$0")"

# Ищем python3 или python.
PY="$(command -v python3 || command -v python || true)"
if [ -z "$PY" ]; then
  echo "❌ Не нашёл Python. Установи его с https://python.org и запусти снова."
  exit 1
fi

# Создаём окружение при первом запуске.
if [ ! -d ".venv" ]; then
  echo "📦 Первый запуск: готовлю окружение (это надо один раз)..."
  "$PY" -m venv .venv
fi

# Активируем окружение.
# shellcheck disable=SC1091
source .venv/bin/activate

# Ставим зависимости один раз (маркер-файл .cache/.deps_ok).
mkdir -p .cache
if [ ! -f ".cache/.deps_ok" ]; then
  echo "⬇️  Ставлю библиотеки (первый раз долго — качается torch)..."
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  touch .cache/.deps_ok
fi

echo "🚀 Запускаю Vision Search. Браузер откроется сам."
exec python app.py
