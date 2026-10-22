#!/usr/bin/env bash
# =============================================================================
# Локальный consumer UI: Django API (:8000) + Vite frontend (:3000)
# Логи в этом терминале; остановка — Ctrl+C.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"
export PYTHONUNBUFFERED=1

API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
PIDS=()
CLEANING_UP=0

usage() {
  cat <<EOF
Использование:
  ./start-web.sh          API + frontend
  ./start-web.sh api      только Django :${API_PORT}
  ./start-web.sh web      только Vite :${WEB_PORT}
  ./start-web.sh help

Переменные:
  API_PORT=8000   WEB_PORT=3000

Полный бот-стек по-прежнему: ./start.sh
EOF
}

cleanup() {
  if [ "$CLEANING_UP" -eq 1 ]; then
    return
  fi
  CLEANING_UP=1
  echo ""
  echo "⏹  Останавливаем API + frontend…"
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  sleep 0.4
  for pid in "${PIDS[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  # Vite/Django иногда остаются вне process group
  pkill -f "manage.py runserver 0.0.0.0:${API_PORT}" 2>/dev/null || true
  pkill -f "vite --port ${WEB_PORT}|vite.*${WEB_PORT}" 2>/dev/null || true
  echo "✅ Готово."
}

trap cleanup EXIT INT TERM

activate_venv() {
  if [ -f "venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
  elif [ -x "./venv/bin/python" ]; then
    export PATH="$ROOT_DIR/venv/bin:$PATH"
  else
    echo "❌ venv не найден. Создайте: python3 -m venv venv && ./venv/bin/pip install -r requirements.txt"
    exit 1
  fi
}

ensure_env() {
  if [ ! -f .env ]; then
    echo "❌ Нет .env — скопируйте .env.example → .env"
    exit 1
  fi
}

ensure_frontend_deps() {
  if [ ! -d frontend/node_modules ]; then
    echo "📦 npm install в frontend/…"
    (cd frontend && npm install)
  fi
}

prefix_logs() {
  local tag="$1"
  sed -u "s/^/[${tag}] /"
}

start_api() {
  echo "🚀 Django API → http://127.0.0.1:${API_PORT}/"
  setsid ./venv/bin/python manage.py runserver "0.0.0.0:${API_PORT}" \
    > >(prefix_logs "api") 2> >(prefix_logs "api" >&2) &
  PIDS+=("$!")
}

start_web() {
  echo "🚀 Vite UI  → http://127.0.0.1:${WEB_PORT}/  (прокси /api → :${API_PORT})"
  (
    cd frontend
    setsid npx vite --host --port "${WEB_PORT}" \
      > >(prefix_logs "web") 2> >(prefix_logs "web" >&2)
  ) &
  PIDS+=("$!")
}

wait_healthy() {
  local url="$1"
  local name="$2"
  local i=0
  local code
  while [ "$i" -lt 40 ]; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    # любой ответ от процесса = жив (404/401 тоже ок)
    if [ -n "$code" ] && [ "$code" != "000" ]; then
      echo "✅ ${name} отвечает (HTTP ${code})"
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  echo "⚠️  ${name} ещё не ответил (${url}) — смотрите логи выше"
}

mode="${1:-both}"

case "$mode" in
  help|-h|--help)
    usage
    exit 0
    ;;
  api)
    activate_venv
    ensure_env
    start_api
    wait_healthy "http://127.0.0.1:${API_PORT}/admin/" "API"
    echo "Работаем. Ctrl+C — стоп."
    wait
    ;;
  web)
    ensure_frontend_deps
    start_web
    wait_healthy "http://127.0.0.1:${WEB_PORT}/" "frontend"
    echo "Работаем. Ctrl+C — стоп."
    wait
    ;;
  both|"")
    activate_venv
    ensure_env
    ensure_frontend_deps
    start_api
    start_web
    wait_healthy "http://127.0.0.1:${API_PORT}/admin/" "API"
    wait_healthy "http://127.0.0.1:${WEB_PORT}/" "frontend"
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  UI:  http://127.0.0.1:${WEB_PORT}/"
    echo "  API: http://127.0.0.1:${API_PORT}/api/v1/"
    echo "  Стоп: Ctrl+C"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    wait
    ;;
  *)
    echo "Неизвестный режим: $mode"
    usage
    exit 1
    ;;
esac
