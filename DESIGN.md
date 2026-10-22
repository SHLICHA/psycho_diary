---
name: Psycho Diary
description: «Тихий вечер» — calm mobile diary UI; promo mockups are the visual source of truth.
colors:
  night: "#1A1A1A"
  night-elevated: "#2C2C2E"
  ink: "#F5F0EA"
  ink-muted: "#A0A0A0"
  paper: "#F0EBE6"
  paper-ink: "#1F1C1A"
  sand: "#E7C79C"
  sand-deep: "#C4A07A"
  sage: "#A3B18A"
  blush: "#C9A3A0"
  danger: "#A66B5C"
  star: "#FFFFFF"
typography:
  display:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "Manrope, system-ui, sans-serif"
    fontSize: "0.6875rem"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.08em"
  hand:
    fontFamily: "Caveat, Neucha, cursive"
    fontSize: "1.35rem"
    fontWeight: 500
    lineHeight: 1.35
    letterSpacing: "normal"
rounded:
  sm: "12px"
  md: "20px"
  lg: "28px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  screen-x: "20px"
components:
  button-primary:
    backgroundColor: "{colors.sand}"
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.pill}"
    padding: "16px 24px"
  button-secondary:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "16px 24px"
  card-paper:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.lg}"
    padding: "20px"
  card-night:
    backgroundColor: "{colors.night-elevated}"
    textColor: "{colors.ink}"
    rounded: "{rounded.lg}"
    padding: "16px"
  fab:
    backgroundColor: "{colors.sand}"
    textColor: "{colors.paper-ink}"
    rounded: "{rounded.pill}"
    size: "64px"
  nav-active:
    textColor: "{colors.sand}"
  chip-selected:
    backgroundColor: "{colors.night}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "10px 16px"
---

# Design System — «Тихий вечер»

## Overview

Psycho Diary’s consumer UI is a **mobile-first** dark evening journal: a quiet room by the window, a warm lamp on paper, soft mood “lights,” and unhurried chrome. The locked visual reference is the set of mockups in [`promo/`](./promo/) (17 screens). Do not revive the discarded Window-night / observatory web MVP.

**Signature motif (source of truth):** [`promo/welcome-desk-reference.png`](./promo/welcome-desk-reference.png) — round window, **crescent moon as cream disk + visible dark disk**, four-point stars, dome pendant + soft cone, open notebook, mug, pen. Also see welcome layout in `promo/photo_4_*.jpg`. Use on welcome, analysis waiting, Premium — not on every dense data screen.

**Product shell:** bottom navigation — Дневник · Архив · center FAB (new entry) · Прогресс · Профиль.

**P0 theme:** only «Тихий вечер». Light / system themes exist in mockups but are out of P0 scope.

## Colors

| Token | Role |
|-------|------|
| `night` | App background |
| `night-elevated` | Secondary cards, chat bubbles, dark list rows |
| `paper` / `paper-ink` | Primary content cards and text on them |
| `sand` / `sand-deep` | Primary CTA, FAB, active nav, lamp glow (`#E7C79C` from promo) |
| `sage` | Positive / calm mood, success checks, “strong suits” chips |
| `blush` | Soft “growth” / caution chips (not errors) |
| `danger` | Destructive actions (delete account) |
| `ink` / `ink-muted` | Primary / secondary text on night surfaces |
| `star` | Speckle texture / rare highlights — keep subtle |

Mood of a day/entry is shown as **soft glowing orbs** (beige / sage / blush), not hard traffic-light badges.

## Typography

- **UI (Manrope):** titles, labels, buttons, stats. Section eyebrows use `label` (small caps / wide tracking).
- **Hand (Caveat / Neucha):** **only** the user’s diary entry text and evening-question prompts that should feel personal. Never for nav, buttons, or legal copy.
- Self-host font files in the frontend build; do not depend on a runtime Google Fonts stylesheet for production.

## Layout

- **Full bleed:** UI fills the viewport width/height. Do **not** trap the app in a ~430px phone column on desktop.
- **Mobile composition** still follows `promo/` (~390 reference for hierarchy and density). Horizontal padding ≈ `screen-x` (scales up on large screens).
- **Rhythm:** 8px grid (`spacing.*`). Generous vertical gaps between sections (`lg` / `xl`); cards are the grouping unit.
- **Readable measures:** long text/forms use `--content-max` / `--form-max`; surfaces and heroes still span the screen.
- **Desktop:** keep the **same vertical composition** as promo, scaled on a full-bleed night stage (centered measure). Prefer scaling one story over awkward left/right splits that crop mock screenshots. Keep the same tokens and motif — not a second brand system.
- **Safe areas:** respect `env(safe-area-inset-*)` under the bottom nav and FAB.
- **Touch:** interactive targets ≥ 44×44 CSS px.

## Elevation & Depth

- Prefer **surface contrast** (night vs paper vs elevated) over heavy drop shadows.
- FAB and mood orbs may use a soft sand/sage **glow** (low opacity, large blur) — sparingly; not on every card.
- Optional faint **starfield** texture at the top of night screens; never noisy full-bleed noise that hurts text contrast.

## Shapes

- Cards: `rounded.lg` (~28px). Inputs/chips: `rounded.md` / `pill`.
- Primary actions and FAB: **pill**.
- Avoid tiny radii and sharp toolbars; the language is soft and continuous.

## Components

- **Primary button:** sand fill, dark text, full-width on mobile forms.
- **Secondary button:** ghost / thin ink border on night, or outlined white on marketing blocks.
- **Paper card:** cream surface for analysis, portrait, notebook entry area (lined paper treatment allowed on compose).
- **Night card:** elevated charcoal for metrics, lists, secondary prompts.
- **Segmented control:** pill track; selected = paper/white fill + dark label (see settings theme switcher / archive tabs).
- **Bottom nav + FAB:** four tabs + center elevated pencil FAB; active tab tint = sand.
- **Chips/tags:** sage filled for strengths; outlined for values; blush outline for growth zones.
- **Waiting steps:** sage check (done), sand ring (active), muted ring (pending).

## Do's and Don'ts

**Do**

- Match structure and hierarchy to the corresponding `promo/` screen before inventing layout.
- Keep copy calm and supportive; RU-primary in P0.
- Use the lamp/window illustration as a brand moment, not wallpaper behind dense forms.
- Build for thumb reach: primary CTA and FAB in the lower half.

**Don't**

- Recreate Window-night / constellation / observatory aesthetics.
- Default to Inter / purple gradients / glassmorphism stacks / emoji-as-icons.
- Put handwritten type on chrome (nav, settings rows, price cards).
- Trap the UI in a centered phone-width column on desktop.
- Invent a second desktop-only brand system unrelated to «Тихий вечер».
- Treat all 17 promo screens as P0 scope — follow `PRODUCT.md` roadmap.
