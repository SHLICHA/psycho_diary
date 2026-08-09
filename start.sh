#!/usr/bin/env bash
# =============================================================================
# Запуск Psycho Diary: Telegram + MAX (+ web + celery)
# Сервисы пишут логи в этот терминал; остановка — Ctrl+C.
# =============================================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-core.settings}"
export PYTHONUNBUFFERED=1

# PIDs лидеров process group (setsid) — по ним гасим всё дерево сервиса
SERVICE_PIDS=()
CLEANING_UP=0

usage() {
    cat <<'EOF'
Использование:
  ./start.sh                Полный стек (web + celery + telegram + max)
  ./start.sh both           То же, что без аргументов
  ./start.sh telegram       Telegram + web + celery (без MAX)
  ./start.sh max            Только MAX (polling или webhook по MAX_TRANSPORT_MODE)
  ./start.sh docker         docker compose up (логи в терминал, Ctrl+C — стоп)
  ./start.sh register-webhook  Зарегистрировать MAX webhook (нужен MAX_WEBHOOK_URL)
  ./start.sh check-webhook  Диагностика MAX webhook
  ./start.sh stop           Остановить локальные процессы скрипта
  ./start.sh help           Справка

Логи всех сервисов идут в этот терминал с префиксами [web]/[celery]/[tg]/[max].
Остановка: Ctrl+C.
EOF
}

read_env_var() {
    local key="$1"
    if [ ! -f .env ]; then
        echo ""
        return
    fi
    grep -E "^${key}=" .env 2>/dev/null | head -1 | cut -d'=' -f2- | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^"//;s/"$//;s/^'\''//;s/'\''$//'
}

mask_secret() {
    local value="$1"
    local prefix_len="${2:-6}"
    if [ -z "$value" ]; then
        echo "<empty>"
        return
    fi
    echo "${value:0:$prefix_len}..."
}

activate_venv() {
    if [ -f "venv/bin/activate" ]; then
        # shellcheck disable=SC1091
        source venv/bin/activate
        echo "✅ venv активирован"
    elif [ -x "./venv/bin/python" ]; then
        export PATH="$ROOT_DIR/venv/bin:$PATH"
        echo "✅ используем ./venv/bin/python"
    else
        echo "❌ venv не найден. Создайте: python3 -m venv venv && pip install -r requirements.txt"
        exit 1
    fi
}

ensure_env_file() {
    if [ ! -f .env ]; then
        echo "❌ Файл .env не найден. Скопируйте .env.example → .env и заполните секреты."
        exit 1
    fi
}

ensure_redis() {
    local broker_url redis_host redis_port
    broker_url="$(read_env_var CELERY_BROKER_URL)"
    redis_host="$(echo "$broker_url" | sed -n 's|redis://\([^:/]*\).*|\1|p')"
    redis_port="$(echo "$broker_url" | sed -n 's|redis://[^:]*:\([0-9]*\).*|\1|p')"
    redis_host="${redis_host:-127.0.0.1}"
    redis_port="${redis_port:-6379}"

    echo "🔴 Redis (${redis_host}:${redis_port})..."
    if redis-cli -h "$redis_host" -p "$redis_port" ping 2>/dev/null | grep -q PONG; then
        echo "✅ Redis доступен"
        return 0
    fi

    if command -v redis-server >/dev/null 2>&1 && { [ "$redis_host" = "127.0.0.1" ] || [ "$redis_host" = "localhost" ]; }; then
        echo "⚠️  Redis не отвечает — пробую redis-server --daemonize yes --port ${redis_port}"
        redis-server --daemonize yes --port "$redis_port"
        sleep 1
        if redis-cli -h "$redis_host" -p "$redis_port" ping 2>/dev/null | grep -q PONG; then
            echo "✅ Redis запущен"
            return 0
        fi
    fi

    echo "❌ Redis недоступен (${redis_host}:${redis_port}). Запустите Redis или docker compose up -d redis"
    exit 1
}

ensure_db() {
    echo "🐘 Проверка БД (migrate)..."
    if ! python manage.py migrate --noinput; then
        echo "❌ Не удалось применить миграции. Проверьте PostgreSQL и DATABASE_* в .env"
        exit 1
    fi
    echo "✅ Миграции OK"
}

check_max_preflight() {
    local transport="$1"
    local enabled token webhook_url

    enabled="$(read_env_var MAX_TRANSPORT_ENABLED)"
    token="$(read_env_var MAX_BOT_TOKEN)"
    webhook_url="${MAX_WEBHOOK_URL_RESOLVED:-$(read_env_var MAX_WEBHOOK_URL)}"
    transport="${transport:-polling}"

    echo "🔎 Preflight MAX..."
    if [ "$enabled" != "true" ] && [ "$enabled" != "1" ] && [ "$enabled" != "True" ]; then
        echo "❌ MAX_TRANSPORT_ENABLED должен быть true"
        return 1
    fi
    if [ -z "$token" ]; then
        echo "❌ MAX_BOT_TOKEN не задан"
        return 1
    fi
    if [ "$transport" != "polling" ] && [ "$transport" != "webhook" ]; then
        echo "❌ MAX_TRANSPORT_MODE должен быть polling или webhook (сейчас: $transport)"
        return 1
    fi
    if [ "$transport" = "webhook" ] && [ -z "$webhook_url" ]; then
        echo "❌ Для webhook нужен BOT_PUBLIC_DOMAIN или MAX_WEBHOOK_URL"
        return 1
    fi

    python manage.py check_max_bot_config
    echo "   ✅ mode=${transport} token=$(mask_secret "$token" 8)"
    return 0
}

# Читает resolved settings после django.setup (BOT_PUBLIC_DOMAIN → mode/URLs).
load_runtime_config() {
    local conf
    conf="$(
        python - <<'PY'
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()
from django.conf import settings

print(getattr(settings, 'MAX_TRANSPORT_MODE', 'polling') or 'polling')
print(getattr(settings, 'MAX_WEBHOOK_URL', '') or '')
print(getattr(settings, 'BOT_PUBLIC_DOMAIN', '') or '')
print(getattr(settings, 'PAYMENT_WEBHOOK_URL', '') or '')
print('1' if getattr(settings, 'PAYMENT_WEBHOOK_ENABLED', False) else '0')
PY
    )"
    MAX_TRANSPORT="$(printf '%s\n' "$conf" | sed -n '1p')"
    MAX_WEBHOOK_URL_RESOLVED="$(printf '%s\n' "$conf" | sed -n '2p')"
    BOT_PUBLIC_DOMAIN_RESOLVED="$(printf '%s\n' "$conf" | sed -n '3p')"
    PAYMENT_WEBHOOK_URL_RESOLVED="$(printf '%s\n' "$conf" | sed -n '4p')"
    PAYMENT_WEBHOOK_ENABLED_RESOLVED="$(printf '%s\n' "$conf" | sed -n '5p')"
    MAX_TRANSPORT="${MAX_TRANSPORT:-polling}"
}

# Запуск команды в отдельной session: stdout/stderr → терминал с префиксом [name]
run_logged() {
    local name="$1"
    shift

    # setsid: отдельная process group — Ctrl+C/cleanup убивают python+sed вместе
    setsid env PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" \
        bash -c '
            tag="$1"
            shift
            "$@" 2>&1 | sed -u "s/^/[${tag}] /"
        ' bash "$name" "$@" &

    local pid=$!
    SERVICE_PIDS+=("$pid")
    echo "✅ [${name}] PID=${pid}"
}

cleanup() {
    if [ "$CLEANING_UP" -eq 1 ]; then
        return
    fi
    CLEANING_UP=1
    trap - INT TERM EXIT

    echo ""
    echo "⏹️  Ctrl+C / stop — останавливаю сервисы..."
    local pid
    for pid in "${SERVICE_PIDS[@]:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            # минус = вся process group (лидер setsid)
            kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
        fi
    done
    sleep 1
    for pid in "${SERVICE_PIDS[@]:-}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
        fi
    done
    # На случай осиротевших процессов без своей group
    pkill -f "manage.py runserver 0.0.0.0:8000" 2>/dev/null || true
    pkill -f "manage.py runbot" 2>/dev/null || true
    pkill -f "manage.py runmaxbot" 2>/dev/null || true
    pkill -f "celery -A core worker" 2>/dev/null || true
    echo "👋 Остановлено"
}

stop_local_processes() {
    echo "🛑 Остановка Psycho Diary (локальные процессы)..."
    pkill -f "manage.py runserver" 2>/dev/null && echo "✅ runserver остановлен" || echo "ℹ️  runserver не был запущен"
    pkill -f "manage.py runbot" 2>/dev/null && echo "✅ runbot остановлен" || echo "ℹ️  runbot не был запущен"
    pkill -f "manage.py runmaxbot" 2>/dev/null && echo "✅ runmaxbot остановлен" || echo "ℹ️  runmaxbot не был запущен"
    pkill -f "celery -A core" 2>/dev/null && echo "✅ celery остановлен" || echo "ℹ️  celery не был запущен"
    sleep 1
    if pgrep -f "manage.py runserver|manage.py runbot|manage.py runmaxbot|celery -A core" >/dev/null 2>&1; then
        echo "⚠️  Принудительная остановка..."
        pkill -9 -f "manage.py runserver" 2>/dev/null || true
        pkill -9 -f "manage.py runbot" 2>/dev/null || true
        pkill -9 -f "manage.py runmaxbot" 2>/dev/null || true
        pkill -9 -f "celery -A core" 2>/dev/null || true
    fi
    echo "👋 Готово (системный Redis/PostgreSQL не трогаем)"
}

start_web() {
    run_logged "web" python manage.py runserver 0.0.0.0:8000
}

start_celery() {
    run_logged "celery" celery -A core worker -B -l info
}

start_telegram() {
    # В polling: MAX отдельно через runmaxbot.
    # В webhook: inbound MAX через [web]; встроенный coordinator в runbot только регистрирует webhook.
    if [ "${MAX_TRANSPORT:-polling}" = "webhook" ]; then
        run_logged "tg" python manage.py runbot
    else
        run_logged "tg" env MAX_TRANSPORT_ENABLED=false python manage.py runbot
    fi
}

start_max_polling() {
    run_logged "max" env MAX_TRANSPORT_ENABLED=true python manage.py runmaxbot
}

print_stack_banner() {
    echo ""
    echo "🎯 Режим MAX: ${MAX_TRANSPORT}"
    echo "   BOT_PUBLIC_DOMAIN: ${BOT_PUBLIC_DOMAIN_RESOLVED:-<empty>}"
    echo "   MAX_WEBHOOK_URL:   ${MAX_WEBHOOK_URL_RESOLVED:-<empty>}"
    if [ "${PAYMENT_WEBHOOK_ENABLED_RESOLVED:-0}" = "1" ]; then
        echo "   PAYMENT_WEBHOOK:  ${PAYMENT_WEBHOOK_URL_RESOLVED}"
    else
        echo "   PAYMENT_WEBHOOK:  disabled (нет BOT_PUBLIC_DOMAIN / PAYMENT_WEBHOOK_URL)"
    fi
}

# Держим терминал: стримим логи, выходим только по Ctrl+C (или если все сервисы умерли)
wait_for_ctrl_c() {
    echo ""
    echo "📜 Логи сервисов ниже. Остановка: Ctrl+C"
    echo "========================================"
    while true; do
        local alive=0
        local pid
        for pid in "${SERVICE_PIDS[@]:-}"; do
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                alive=1
                break
            fi
        done
        if [ "$alive" -eq 0 ]; then
            echo ""
            echo "⚠️  Все сервисы завершились (смотрите логи выше)."
            exit 1
        fi
        sleep 1
    done
}

MODE="${1:-both}"

case "$MODE" in
    help|-h|--help)
        usage
        exit 0
        ;;
    stop)
        stop_local_processes
        exit 0
        ;;
    docker)
        ensure_env_file
        activate_venv
        load_runtime_config
        echo "🐳 docker compose up (логи в терминал, Ctrl+C — стоп)..."
        echo "   MAX mode=${MAX_TRANSPORT} domain=${BOT_PUBLIC_DOMAIN_RESOLVED:-<empty>}"
        if [ "$MAX_TRANSPORT" = "webhook" ]; then
            echo "ℹ️  webhook: max_bot не поднимаем (events → web /api/max/webhook/)"
            exec docker compose up db redis web celery_worker celery_beat telegram_bot nginx
        fi
        exec docker compose up db redis web celery_worker celery_beat telegram_bot max_bot nginx
        ;;
    check-webhook)
        ensure_env_file
        activate_venv
        load_runtime_config
        WEBHOOK_URL="${MAX_WEBHOOK_URL_RESOLVED}"
        if [ -z "$WEBHOOK_URL" ]; then
            echo "❌ Нет MAX_WEBHOOK_URL (задайте BOT_PUBLIC_DOMAIN или MAX_WEBHOOK_URL)"
            exit 1
        fi
        echo "🔍 GET $WEBHOOK_URL"
        curl -sS -L --connect-timeout 5 --max-time 12 -o /tmp/max_webhook_check.body -w "HTTP %{http_code}\n" -X GET "$WEBHOOK_URL" || true
        echo "--- body ---"
        head -c 400 /tmp/max_webhook_check.body 2>/dev/null || true
        echo ""
        if [ -n "${PAYMENT_WEBHOOK_URL_RESOLVED}" ]; then
            echo "🔍 Payment webhook URL: ${PAYMENT_WEBHOOK_URL_RESOLVED}"
            echo "   (пропишите этот URL в кабинете ЮKassa)"
        fi
        python manage.py check_max_bot_config || true
        exit 0
        ;;
    register-webhook)
        ensure_env_file
        activate_venv
        load_runtime_config
        if ! check_max_preflight "$MAX_TRANSPORT"; then
            exit 1
        fi
        if [ "$MAX_TRANSPORT" != "webhook" ]; then
            echo "❌ register-webhook нужен webhook-режим (задайте BOT_PUBLIC_DOMAIN или MAX_TRANSPORT_MODE=webhook)"
            exit 1
        fi
        python - <<'PY'
import asyncio
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.conf import settings
from bot.transports.max.client import MaxClient


async def main() -> None:
    url = (getattr(settings, "MAX_WEBHOOK_URL", "") or "").strip()
    if not url:
        raise SystemExit("MAX_WEBHOOK_URL пуст — задайте BOT_PUBLIC_DOMAIN")
    client = MaxClient(
        api_token=settings.MAX_BOT_TOKEN,
        base_url=settings.MAX_API_BASE_URL,
        timeout_seconds=settings.MAX_API_TIMEOUT_SECONDS,
    )
    try:
        ok = await client.register_webhook(
            webhook_url=url,
            update_types=["message_created", "bot_started", "message_callback"],
        )
    finally:
        await client.close()
    if not ok:
        raise SystemExit("register_webhook вернул False")
    print(f"✅ Webhook зарегистрирован: {url}")
    pay = getattr(settings, "PAYMENT_WEBHOOK_URL", "") or ""
    if pay:
        print(f"ℹ️  ЮKassa webhook (кабинет): {pay}")


asyncio.run(main())
PY
        exit 0
        ;;
esac

ensure_env_file
activate_venv
ensure_redis
ensure_db

trap cleanup INT TERM EXIT

load_runtime_config
echo "📋 Resolved: MAX_TRANSPORT_MODE=${MAX_TRANSPORT} BOT_PUBLIC_DOMAIN=${BOT_PUBLIC_DOMAIN_RESOLVED:-<empty>}"

case "$MODE" in
    max)
        if ! check_max_preflight "$MAX_TRANSPORT"; then
            exit 1
        fi
        print_stack_banner
        if [ "$MAX_TRANSPORT" = "polling" ]; then
            echo "🎯 MAX: Long Polling"
            start_max_polling
        else
            echo "🎯 MAX webhook → ${MAX_WEBHOOK_URL_RESOLVED:-/api/max/webhook/}"
            start_web
        fi
        wait_for_ctrl_c
        ;;
    telegram)
        echo "🎯 Стек: web + celery + telegram"
        print_stack_banner
        start_web
        start_celery
        start_telegram
        wait_for_ctrl_c
        ;;
    both|default|"")
        if ! check_max_preflight "$MAX_TRANSPORT"; then
            exit 1
        fi
        echo "🎯 Полный стек: web + celery + telegram + max"
        print_stack_banner
        start_web
        start_celery
        start_telegram
        if [ "$MAX_TRANSPORT" = "polling" ]; then
            start_max_polling
        else
            echo "ℹ️  MAX webhook через [web] (${MAX_WEBHOOK_URL_RESOLVED:-/api/max/webhook/})"
            echo "ℹ️  Отдельный runmaxbot не запускается (polling и webhook взаимоисключаемы)"
        fi
        wait_for_ctrl_c
        ;;
    *)
        echo "❌ Неизвестный режим: $MODE"
        usage
        exit 1
        ;;
esac
