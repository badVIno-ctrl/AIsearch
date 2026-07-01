@echo off
REM ============================================================
REM  Vision Search - запуск на Windows двойным кликом.
REM  Скрипт сам создаёт окружение и ставит зависимости.
REM  Нужен только установленный Python 3.9+ (галочка Add to PATH).
REM ============================================================
setlocal
cd /d "%~dp0"

REM Ищем Python.
where python >nul 2>nul
if errorlevel 1 (
  echo [X] Не нашёл Python. Установи его с https://python.org
  echo     и обязательно поставь галочку "Add Python to PATH".
  pause
  exit /b 1
)

REM Создаём окружение при первом запуске.
if not exist ".venv" (
  echo [*] Первый запуск: готовлю окружение (один раз)...
  python -m venv .venv
)

call .venv\Scripts\activate.bat

if not exist ".cache" mkdir ".cache"
if not exist ".cache\.deps_ok" (
  echo [*] Ставлю библиотеки (первый раз долго - качается torch)...
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
  echo ok> ".cache\.deps_ok"
)

echo [*] Запускаю Vision Search. Браузер откроется сам.
python app.py
pause
