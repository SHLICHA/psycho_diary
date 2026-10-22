# Psycho Diary — consumer frontend

Mobile-first PWA («Тихий вечер»). Канон: [`../PRODUCT.md`](../PRODUCT.md), [`../DESIGN.md`](../DESIGN.md), макеты [`../promo/`](../promo/).

## Стек

Vite + React + TypeScript + `vite-plugin-pwa` → позже Capacitor.

## Сейчас

- Welcome (`/`) по promo + живые CTAs
- Login / Register → JWT
- Onboarding (`/onboarding`) — имя, город/TZ, напоминание, согласие
- Home «Дневник» (`/app`) + bottom nav (архив/прогресс/профиль — заглушки)
- Dev-прокси: `/api` → `http://127.0.0.1:8000`

## Запуск

Из корня репозитория (API + UI одним процессом):

```bash
./start-web.sh
```

- UI: http://127.0.0.1:3000/
- API: http://127.0.0.1:8000/api/v1/
- Стоп: `Ctrl+C`

Только API / только UI: `./start-web.sh api` · `./start-web.sh web`

Полный бот-стек (Telegram/MAX/Celery): `./start.sh`
