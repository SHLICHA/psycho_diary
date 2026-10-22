# Установка скилов Why not! на другой машине

Документ описывает **все скилы**, которыми пользуется этот проект в Cursor, и как поднять такой же набор на новом компьютере.

Каталог скилов: [skills.sh](https://skills.sh/) · CLI: `npx skills` ([vercel-labs/skills](https://github.com/vercel-labs/skills)).

## Что уже есть в репозитории

| Путь | Назначение |
|------|------------|
| [`skills-lock.json`](./skills-lock.json) | Lock проектных скилов (thinking-pack) |
| `.agents/skills/` | Установленные **проектные** скилы (после `experimental_install`) |
| `.cursor/skills/` | Локальные скилы проекта (`ui-design-brain`, `mobile-design`) — сейчас в `.gitignore` |

Глобальные скилы живут вне репо: `~/.agents/skills/` и `~/.cursor/skills/`.

---

## Быстрый старт (новая машина)

Требования: **Node.js 18+** (лучше 22+), установленный **Cursor**, доступ в интернет, `git`.

```bash
# 0. Клонировать проект и перейти в корень
git clone <url-репозитория> why-not
cd why-not

# 1. Основной пакет рабочих скилов (~160 playbooks: audit/plan/workflow/…)
npx @kensaurus/skills --auto --dry-run   # превью
npx @kensaurus/skills --auto             # установка
npx @kensaurus/skills --auto --verify    # проверка

# 2. Проектный lock из skills-lock.json → .agents/skills/
npx skills experimental_install

#    (эквивалент вручную:)
#    npx skills add samhvw8/thinking-skills -y \
#      --skill ambition --skill council --skill creative \
#      --skill debate --skill heavy-think

# 3. Дизайн-скилы, которые правила проекта вызывают явно
npx impeccable install -y --providers=cursor --scope=global
# или: npx skills add pbakaus/impeccable -g -y

npx skills add marvkr/better-design -g -y
npx skills add vercel-labs/skills --skill find-skills -g -y

# 4. Скилы UI, которые лежат в .cursor/skills проекта
mkdir -p .cursor/skills
git clone https://github.com/carmahhawwari/ui-design-brain.git \
  .cursor/skills/ui-design-brain

# mobile-design: точного публичного пакета под нашу копию нет —
# скопируйте с этой машины (см. § «Перенос каталогов»)
#   rsync -a /path/from/.cursor/skills/mobile-design/ .cursor/skills/mobile-design/

# 5. Опционально: third-party, если нужны те же внешние гайды
npx skills add nextlevelbuilder/ui-ux-pro-max-skill -g -y
npx skills add emilkowalski/skills -g -y
npx skills add vercel-labs/web-interface-guidelines -g -y

# 6. Проверка
npx skills list
npx skills list -g | head
```

После установки **перезапустите Cursor** (или откройте проект заново), чтобы агент подхватил скилы.

---

## Слои скилов (как устроено)

```
┌─────────────────────────────────────────────────────────────┐
│  A. Проект (в репо / рядом с репо)                          │
│     skills-lock.json → .agents/skills/                      │
│       ambition, council, creative, debate, heavy-think      │
│     .cursor/skills/                                         │
│       ui-design-brain, mobile-design                        │
├─────────────────────────────────────────────────────────────┤
│  B. Глобально на машине (~/.agents/skills, ~/.cursor/skills)│
│     @kensaurus/skills  — основной набор playbooks           │
│     pbakaus/impeccable — /impeccable critique|polish|…      │
│     marvkr/better-design — skill + MCP Better Design        │
│     vercel-labs/skills@find-skills                          │
│     (+ опционально thirdparty-*)                            │
├─────────────────────────────────────────────────────────────┤
│  C. MCP (не скилы, но нужны тем же правилам)                │
│     Framewise (@framewise/mcp)                              │
│     Better Design (https://better-design.com/api/mcp)       │
└─────────────────────────────────────────────────────────────┘
```

Правила пользователя в Cursor ссылаются на `ui-design-brain`, `mobile-design`, `impeccable`, `test-exploratory`, `scan_page` (Framewise) и т.д. Без слоя B/C агент на новой машине увидит только то, что установите вы.

---

## A. Проектные скилы (`skills-lock.json`)

Источник: [samhvw8/thinking-skills](https://github.com/samhvw8/thinking-skills).

| Скил | Зачем |
|------|--------|
| `ambition` | Амбициозная постановка / переписывание промпта |
| `council` | Мультиагентный «совет» |
| `creative` | Генерация небанальных идей |
| `debate` | Давление на решение / спор |
| `heavy-think` | Тяжёлое мышление, brainstorm / perspectives |

Восстановление после клона:

```bash
cd /path/to/why-not
npx skills experimental_install
# алиасы: npx skills i   |   npx skills install
```

Проверка:

```bash
npx skills list          # должны быть 5 project skills
ls .agents/skills
```

Файл `skills-lock.json` **нужно коммитить** в git. Каталог `.agents/skills/` можно не коммитить — он восстанавливается командой выше.

---

## B. Глобальный пакет Kenji (основной объём)

Источник / установщик: [`@kensaurus/skills`](https://www.npmjs.com/package/@kensaurus/skills) · репо [kensaurus/skills](https://github.com/kensaurus/skills) (также фигурирует как `kensaurus/cursor-kenji`).

```bash
npx @kensaurus/skills --auto
```

Ставит скилы в `~/.cursor/skills/` и копию в `~/.agents/skills/`, плюс commands/rules/hooks по желанию установщика.

### Каталог имён (снимok с рабочей машины, ~160 скилов)

**audit-*** (31): accessibility, analytics, auth-flows, backend-architecture, bundle-size, cicd, code-quality, code-review, codemod-safety, db-schema, doctrine, env-parity, fe-api, gate-logic, i18n, infra-cost, langfuse-llm, llm-security, monetization-iap, payment-system, performance, realworld, registry-listing, resilience, responsive, security, skill-conflicts, ui-states, uiux-design-system, ux, ux-journeys

**plan-*** (23): aeo-readiness, antislop, aso, backup-dr, capacitor-hardening, data-integrity, dead-code, dependency-provenance, docs-sync, error-handling, gtm, input-validation, llm-cost-guardrails, mobile-readiness, perf-audit, pricing, privacy-compliance, rls-audit, secrets-audit, security-audit, stub-checker, test-coverage, uiux-unification

**workflow-*** (21): build-feature, coding-discipline, environment-ready, feature-flag, feedback-to-closure, fix-and-ship, git-commit, green-repo, grilling, gtm, housekeep, launch-ready, merge-conflicts, onboard, parallel-agents, pr, quality-gate, refactor, release-prep, ship-and-observe, spec-tdd

**enhance-*** (21): agent-guardrails, arch-boundaries, capacitor-ui, email-deliverability, growth-loops, lifecycle-email, motion, onboarding, pwa, readability, readme, skill-prompts, web-conversion, web-forms, web-instant-nav, web-landing, web-redesign, web-seo, web-ui, web-ux, web-web3d

**design-*** (10): api, canvas, email, frontend, generative-art, mobile-first, motion, prd, system, theme

**test-*** (8): exploratory, load, mutation, playwright, qa, red-team, unit, visual-regression

**backend-*** (5): db-performance, error-handling, observability, patterns, realtime

**docs-*** (6): adr, coauthor, comparison-pages, domain-modeling, launch-kit, writer

**mobile-*** (5): capacitor-platform, emulator-start, emulator-test, rn-performance, rn-screen

**housekeep-*** (4): backlog, dead-code, design, gates

**debug-*** (3): error, fe-be-integration, sentry-monitor

**deploy-*** (2): npm, verify

**iterate-*** (3): agent-harness, gtm-weekly, post-launch

**meta-*** (2): mcp-builder, skill-creator

**прочее:** burndown-full, complete-everything, data-pipeline, data-visualization, handoff, research, protocol-browser-anti-stall, mushi-health, mushi-integration

Именно этот пакет закрывает правила вроде «после UI → Framewise / exploratory», «plan-* / audit-* / workflow-*».

---

## C. Отдельные дизайн-скилы

### Impeccable

```bash
npx impeccable install -y --providers=cursor --scope=global
# альтернатива: npx skills add pbakaus/impeccable -g -y
```

В чате: `/impeccable critique|polish|typeset|…`. В проекте уже есть `DESIGN.md`, `PRODUCT.md`, `.impeccable/`.

### Better Design (skill + MCP)

```bash
npx skills add marvkr/better-design -g -y
```

MCP в Cursor (`~/.cursor/mcp.json` или Settings → MCP):

```json
{
  "mcpServers": {
    "better-design": {
      "url": "https://better-design.com/api/mcp",
      "headers": {
        "Authorization": "Bearer <ВАШ_ТОКЕН_С_better-design.com>"
      }
    }
  }
}
```

Токен взять в личном кабинете Better Design. **Не коммитьте** живой Bearer в git.

Официальный setup: [github.com/marvkr/better-design](https://github.com/marvkr/better-design#setup).

### UI Design Brain (проектный)

```bash
git clone https://github.com/carmahhawwari/ui-design-brain.git \
  .cursor/skills/ui-design-brain
```

Или глобально: `~/.cursor/skills/ui-design-brain`.

### mobile-design (проектный)

Каталог `.cursor/skills/mobile-design` на рабочей машине — локальная копия (Apple HIG / touch-targets). Публичного one-liner под **эту** копию нет.

**Перенос с текущей машины:**

```bash
# на старой машине
tar czf mobile-design-skill.tgz -C /path/to/why-not/.cursor/skills mobile-design

# на новой
mkdir -p why-not/.cursor/skills
tar xzf mobile-design-skill.tgz -C why-not/.cursor/skills
```

### find-skills

```bash
npx skills add vercel-labs/skills --skill find-skills -g -y
```

---

## D. MCP, которые правила проекта ожидают

### Framewise (`scan_page`)

```json
{
  "mcpServers": {
    "framewise": {
      "command": "npx",
      "args": ["-y", "@framewise/mcp"]
    }
  }
}
```

После UI-правок правила просят `scan_page` на `http://localhost:3000` (или ваш dev URL).

### Better Design

См. § C выше.

Свести оба сервера в один `~/.cursor/mcp.json` и перезапустить Cursor.

---

## E. Опциональные third-party

На рабочей машине стоят как `thirdparty-*` (часто поверх Kenji / ручная установка):

| Локальное имя | Установка |
|---------------|-----------|
| `thirdparty-ui-ux-pro-max` | `npx skills add nextlevelbuilder/ui-ux-pro-max-skill -g -y` |
| `thirdparty-emil-design-eng` | `npx skills add emilkowalski/skills -g -y` |
| `thirdparty-web-interface-guidelines` | `npx skills add vercel-labs/web-interface-guidelines -g -y` |

`luongnv89-code-optimizer` — локальный скил оптимизации кода; при необходимости скопируйте каталог с текущей машины (`~/.agents/skills/luongnv89-code-optimizer` или `~/.cursor/skills/…`).

---

## Перенос каталогов «как есть» (без переустановки)

Если нужна **байт-в-байт** копия текущей машины:

```bash
# НА СТАРОЙ МАШИНЕ
cd ~
tar czf cheers-skills-backup.tgz \
  .agents/skills \
  .agents/.skill-lock.json \
  .cursor/skills \
  .cursor/mcp.json

# + из репо (если ещё не в git):
#   why-not/skills-lock.json
#   why-not/.cursor/skills/
#   why-not/.agents/skills/

# НА НОВОЙ МАШИНЕ
cd ~
tar xzf cheers-skills-backup.tgz
# поправьте пути/токены в ~/.cursor/mcp.json
# откройте проект в Cursor и перезапустите окно
```

Минус: бэкап тяжелее и хуже обновляется. Предпочтительнее команды из «Быстрого старта».

---

## Проверка, что всё на месте

```bash
cd /path/to/why-not

# Проектный lock
test -f skills-lock.json && npx skills list | grep -E 'ambition|heavy-think'

# Глобальный Kenji + дизайн
test -d ~/.agents/skills/workflow-onboard && echo kenji:ok
test -d ~/.agents/skills/impeccable -o -d ~/.cursor/skills/impeccable && echo impeccable:ok
test -d ~/.agents/skills/better-design && echo better-design:ok

# Проектные UI-скилы
test -f .cursor/skills/ui-design-brain/SKILL.md && echo ui-design-brain:ok
test -f .cursor/skills/mobile-design/SKILL.md && echo mobile-design:ok
```

В Cursor Agent: спросите «какие скилы доступны для UI?» — должны находиться `ui-design-brain`, `impeccable`, `better-design`.

---

## Обновление

```bash
# Kenji
npx @kensaurus/skills --auto

# Skills CLI (глобальные GitHub-backed)
npx skills update -g -y

# Только проект из lock
cd /path/to/why-not && npx skills update -p -y

# Impeccable
npx impeccable update
```

---

## Частые проблемы

| Симптом | Что сделать |
|---------|-------------|
| Агент не видит скил | Перезапуск Cursor; путь должен быть `*/skills/<name>/SKILL.md` |
| `experimental_install` пустой | Вы в корне репо? Есть `skills-lock.json`? |
| Framewise / Better Design «нет tools» | Проверить MCP в Settings, токен, `npx -y @framewise/mcp` |
| Windows + symlink | `npx skills add … --copy` |
| Дубли Kenji + lock | Нормально: thinking-skills могут быть и в проекте, и глобально |

---

## Минимальный чеклист «машина готова к Why not!»

- [ ] Node 18+
- [ ] Cursor установлен
- [ ] `npx @kensaurus/skills --auto`
- [ ] `npx skills experimental_install` в корне репо
- [ ] Impeccable + Better Design skill
- [ ] `.cursor/skills/ui-design-brain` (+ `mobile-design` скопирован)
- [ ] MCP: Framewise + Better Design (свой токен)
- [ ] Cursor перезапущен
- [ ] `npx skills list` / `list -g` показывают ожидаемое

---

*Снимок состава глобальных скилов актуален на дату создания документа (машина разработчика). Точный список после установки Kenji может чуть отличаться по версии пакета — ориентируйтесь на `npx @kensaurus/skills --auto --verify`.*
