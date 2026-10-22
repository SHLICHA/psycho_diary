# Product

<!-- impeccable:product-schema 1 -->

## Platform

web (mobile-first PWA) → later native shell (Capacitor)

## Users

Primary user: someone who wants a **regular psychological diary** with AI analysis of each entry — a day-to-day analog of reflective work with a psychologist (insight and recommendations), not acute crisis triage.

## Product Purpose

An AI-assisted psychological diary that helps people capture thoughts and emotions, receive per-entry analysis, and build longer-horizon self-understanding over time. Success means the person returns to write, trusts the analysis enough to continue, and sees a coherent evolving picture of themselves across days and weeks.

## Positioning

**Long memory and a growing psychological profile.** Neighboring “ChatGPT in a messenger” products can answer in the moment; this product’s distinct claim is longitudinal continuity: entries feed daily/weekly analysis and an updating psychoprofile that compounds with use.

## Operating Context

- Primary surfaces today: **Telegram** and **VK MAX** bots (chat UI), backed by Django, Celery, and related services.
- Core ritual: write (text/voice) → AI analysis (mood, comment, recommendations; optional clarifications) → optional day/week synthesis → profile update → optional tasks, streaks, reminders.
- Account identity can span Telegram / MAX / web via email-linked merge flows.
- Product is **already in production** (~1 year on a live server). Operational continuity matters as much as new features.
- **Consumer client** is rebuilt as a **mobile-first PWA** (“Add to Home Screen” first), sharing `/api/v1/` with Telegram/MAX. Same Django host serves API; SPA is a separate `frontend/` build. Later: wrap the same build with **Capacitor** for store apps.

## Stack

- **Backend:** Django monolith (API, bots, Celery, admin). Schema and bot channels stay untouched unless explicitly approved.
- **Consumer UI (locked):** **Vite + React + TypeScript + PWA** (`vite-plugin-pwa`), JWT against existing `/api/v1/`.
- **Mobile path:** PWA install / Home Screen → later Capacitor over the same `dist/`.
- **Not chosen for consumer UI:** Django templates/HTMX as the primary app shell; Next.js as the default host.

## Capabilities and Constraints

Confirmed capabilities (existing product): diary entries; per-entry AI analysis; clarification questions; combined day analysis; weekly analysis; psychoprofile; therapy-style tasks; awareness level / streaks; AI therapy chat; tokens and premium; RU/EN message catalogs; settings (timezone, notifications, auto-analysis); privacy (encryption, account deletion); help/feedback; onboarding.

Hard constraints for all future work:

- **Do not break the production database schema** or require destructive migrations that invalidate a year of live data. Evolve schema only with additive, backward-compatible changes unless explicitly approved.
- **Calm, supportive tone** — not clinical diagnosis language.
- **Two languages (RU/EN) remain the product ideal**; current real usage is primarily one language (RU). Keep i18n paths intact; do not remove the second language. Bot `messages/` RU+EN catalogs stay the bilingual source of truth. **Consumer UI copy is RU-primary** in P0.
- **Responsive full-bleed UI:** mobile-first composition from `promo/`, but the app **stretches to the viewport** on phone and desktop (no phone-frame column). Desktop gets adapted layouts (e.g. welcome split), not a separate product visual system.

## Consumer UI roadmap (locked)

**Visual / UX source of truth:** `promo/*.jpg` (17 mobile mockups). Direction name: **«Тихий вечер»**. Spec: `DESIGN.md`.

**P0 (ship ritual):**

1. Welcome (no required Telegram CTA in P0)
2. Register / login / password reset — **email + password**
3. Onboarding (name, city/TZ, reminder time, medical disclaimer consent)
4. Home «Дневник»
5. New entry → waiting («психолог читает») → analysis card
6. PWA: web app manifest, icons, installable / Add to Home Screen

**P1+ (same design system):** archive (calendar/day), profile portrait, settings, progress, tasks, therapy chat, Premium/tokens UI, messenger link.

Broader bot feature parity is later; do not block P0 on full parity.

## Brand Commitments

- Voice: calm, supportive, reflective.
- Product name: **Psycho Diary**.
- Web visual direction (locked): **«Тихий вечер»** — dark charcoal night, warm lamp/window illustration motif, cream “paper” cards, sand/peach accent, mood “lights”, handwritten entry text. See `DESIGN.md`. Previous Window-night study MVP is discarded and must not be revived.
- Theme switcher in mockups (Тихий вечер / Светлая / Как в системе): **P0 ships «Тихий вечер» only**; other themes later.

## Evidence on Hand

- Product and feature description: `README.txt`
- Design mockups: `promo/`
- Design system: `DESIGN.md`
- Frontend stack ADR: `docs/adr-frontend-pwa.md`
- Technical/product docs: e.g. `BOTS_TECHNICAL_GUIDE.md`, `FRONTEND_API_REFERENCE.md`, `AI_INSTRUCTIONS.md`
- Runtime UX copy: `messages/` (ru, en)
- AI prompts: `prompts/`
- Live production system with real user data — future work must not fabricate testimonials, benchmarks, or pricing claims beyond what the codebase and operators confirm.

## Product Principles

1. **Continuity over novelty** — protect live data, schemas, and existing user journeys first.
2. **Memory compounds** — every feature should strengthen longitudinal understanding, not replace it with one-off chat.
3. **Daily reflective loop** — entry → analysis → optional depth (day/week/tasks) stays the core job.
4. **Calm trust** — tone and privacy practices must keep the diary a safe place to write.
5. **i18n-ready even if usage is skewed** — prefer bilingual-capable changes over RU-only shortcuts that erase EN paths.
6. **One UI codebase** — PWA and future Capacitor share the React build; do not fork a second visual product.

## Identity & Web Auth

One person = one `User`. Channels: `telegram_id`, `max_id`, email (`email_hash`), password; consumer client uses **JWT** (`/api/v1/`).

- **P0 web-first:** register/login with **email + password** only. Messenger login CTAs are optional later.
- **Bot-first:** set / reset web password via **bot confirm** on the same User (`/recover` → TG/MAX → `/auth/set-password/`). Messenger deep-link login UI later.
- **Email** is the merge/claim key (`IdentityPolicyService` / `EmailMergeService`). Never create a second User for an email that already belongs to someone.
- **Conflict:** dual-confirm merge (TG/MAX callbacks); if the email owner has no messenger → email OTP. Data merge gated by `EMAIL_MERGE_EXECUTE_ENABLED`.
- **Password reset:** primary while SMTP is off — bot claim (`POST /api/v1/web-access/claim/` + set-password). Email link/token when SMTP is configured.

## Accessibility & Inclusion

Consumer UI target: **WCAG AA** for text and controls; touch targets ≥ 44×44 CSS px; respect safe-area insets on notched phones. Messenger platforms still own bot chrome.
