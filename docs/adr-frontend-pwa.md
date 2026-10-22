# ADR: Consumer frontend — Vite + React + PWA → Capacitor

## Status

Accepted (2026-10-22).

## Context

Consumer web UI was reset (previous Window-night Django `webui` removed). New visual direction is locked to mobile mockups in `promo/` («Тихий вечер»). Product path: **installable mobile web first** (Add to Home Screen), then a **store app** from the same UI codebase. Backend already exposes JWT `/api/v1/`; bots remain on Django.

## Decision

1. Build consumer UI as **`frontend/`**: **Vite + React + TypeScript**.
2. Ship as **PWA** (`vite-plugin-pwa`, web app manifest, icons) for Home Screen install.
3. Talk to the existing Django API with **JWT** (email + password in P0).
4. Later wrap the same production `dist/` with **Capacitor** for native shells — do not fork a second UI.
5. **Not** using Django templates/HTMX as the primary app shell; **not** defaulting to Next.js while Django owns the API.

## Consequences

- Deploy: static SPA (CDN or Django/`whitenoise`/nginx) + existing API host; CORS/`WEB_APP_URL` must allow the SPA origin.
- Deep links and password-reset URLs must target the SPA routes, not removed session `webui` paths.
- Design tokens and screen composition live in `DESIGN.md` / `promo/`; agents must not invent a parallel visual system.
- P0 scope is the diary ritual + auth + PWA installability (`PRODUCT.md`); archive/progress/chat/premium follow under the same system.

## References

- `PRODUCT.md` — platform, P0, auth
- `DESIGN.md` — «Тихий вечер»
- `promo/` — mockup source of truth
- `FRONTEND_API_REFERENCE.md` — API contracts
