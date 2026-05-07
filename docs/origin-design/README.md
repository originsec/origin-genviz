---
name: origin-design
description: Use this skill to generate well-branded interfaces and assets for Origin (the agent-observability platform — "Make digital labor observable."), either for production or throwaway prototypes/mocks/etc. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the README.md file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. Always link `colors_and_type.css` and load Fira Code + Inter from the Google Fonts CDN; copy `assets/logo-origin-wordmark.svg` when the wordmark is needed.

If working on production code, you can copy assets and read the rules in README.md to become an expert in designing with this brand. Treat `colors_and_type.css` as the canonical token reference; the dark-theme overrides at the bottom of that file are the source of truth for `[data-theme="dark"]`.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions (audience, surface — customer / employee / dashboard, fidelity, variations), and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

Key constraints to internalise before producing anything:
- ~90% warm neutrals. Accents (jade / ember / iris / bronze) appear once per moment, never as ambient surfaces.
- Two type families only: Fira Code for display/subheads/labels/metadata, Inter for body/UI. Display tracking −3 to −4%, uppercase labels +8%, body never below 14 px.
- Status colours (active / idle / warning / danger) are functional — never decorative.
- Data-viz colours are chart-only.
- Internal-comms palette (blush / lavender / sage / teal / steel / etc) is **employee-facing only**, never customer-facing.
- Iconography is Lucide at stroke 1.5, round caps & joins. No emoji in product/marketing.
- No gradient backgrounds, no full-bleed stock photography, no rounded-card-with-coloured-left-border patterns.


# Origin Design System

> Make digital labor observable.

A warm-neutral, code-native design system for **Origin** — a platform that captures the full semantic trace of every agent action and makes it queryable for security, compliance, and engineering teams.

This system is the source of truth for Origin's customer-facing product, marketing, and internal communications surfaces. It encodes the brand's tone (precise, technical, plain-spoken), its visual vocabulary (warm neutrals, monospaced display, restrained accents), and its component library.

---

## Source materials

This design system was assembled from a single brand specification document provided in chat. **No codebase, Figma file, or live screens were available** — the UI kits below are interpretive recreations grounded in that spec, not pixel-faithful copies of a shipped product. When source artifacts become available we should regenerate the kits against them.

- `assets/logo-origin-wordmark.svg` — Origin wordmark, 3857×1083 viewBox, 11 paths. Provided by the user.
- Token spec — pasted into chat. All colour, type, and usage rules below are lifted directly from it.

---

## Index

```
.
├── README.md                       ← you are here
├── SKILL.md                        ← agent skill manifest (cross-compatible with Claude Code)
├── colors_and_type.css             ← all design tokens as CSS custom properties + element defaults
│
├── assets/
│   └── logo-origin-wordmark.svg    ← primary horizontal wordmark
│
├── preview/                        ← Design System tab cards (registered via register_assets)
│   ├── _card.css
│   ├── logo.html
│   ├── colors-neutrals.html  · -accents · -status · -viz · -internal-comms · -borders
│   ├── type-display.html · -subhead · -body · -scale · -hierarchy
│   ├── spacing-scale.html · radii.html · shadows.html
│   ├── components-buttons.html · -inputs · -tags · -card · -table
│   └── iconography.html
│
└── ui_kits/
    ├── marketing/                  ← landing page recreation
    │   ├── README.md, index.html
    │   └── Header · Hero · FeatureRow · StatsBand · CTA · Footer .jsx
    └── internal_comms/             ← employee-facing comms templates
        ├── README.md, index.html
        └── TownHallPoster · WelcomeCard · StatusUpdate · Tiles .jsx
```

---

## Content fundamentals

**Voice.** Plain-spoken, technical, declarative. Origin sells visibility, not vibes. Sentences are short. Verbs are concrete (*capture, query, surface, flag*). Adjectives are rare; when they appear, they are functional (*atypical, semantic, full*) — never aspirational.

**Person.** Mostly third-person product-as-subject ("Origin captures…", "Sessions analysed…"). Occasionally second-person for action prompts ("Connect endpoint", "View trace"). Never first-person plural in product copy.

**Casing.** Sentence case for body and most UI labels. Title Case for display headlines (`The Semantic Era`, `Agent Observability`). ALL CAPS, +8% tracking, for status and metadata labels only (`SESSIONS`, `LAST SEEN`, `STATUS · ATYPICAL`). Never ALL CAPS for a full sentence.

**Tone dial.** Confident, not hyped. The product is technical; let the technical detail be the proof.
- ✅ "Capture overhead < 80 ms."
- ❌ "Lightning-fast! 🚀 Industry-leading observability!"

**Numbers.** Tabular figures (`font-variant-numeric: tabular-nums`). Comma thousands separators. Units are spaced (`80 ms`, `2 s ago`, `1,247 sessions`). Time is monospaced and absolute when precise (`14:02:08.121`), relative when approximate (`2 s ago`).

**Punctuation.** En-dash (–) for ranges, em-dash (—) for asides, middle dot (·) as a separator in metadata. No exclamation points. Periods at the end of every full sentence — including in cards.

**Specific examples (from the spec).**
- Display: *"The Semantic Era"*, *"Agent Observability"*, *"Every Endpoint."*
- Body: *"Origin captures the full semantic trace of every agent action and makes it queryable for security, compliance, and engineering teams."*
- Labels: *"● Active"*, *"● Idle"*, *"● Atypical"*, *"SECTION LABEL · STATUS · METADATA"*
- Stats: *"Sessions  1,247"*, *"Prompts Analyzed  84,391"*

**Emoji.** Not used in product or marketing surfaces. The internal-comms newsletter may use a single, contextual emoji (🧵 for "thread", 📌 for "pinned") — never decoratively, never in headlines.

---

## Visual foundations

**Colour identity.** ~90% warm neutrals. Bone (`#FFF1E5`), surface (`#FFFCF8`), and carbon (`#33302E`) carry virtually all real estate. The four accents (jade, ember, iris, bronze) appear once per moment — a tag, a callout, a section rule — never as ambient backgrounds. Status colours are reserved for system state. Viz colours never leave charts. Internal-comms colours never leave internal-comms surfaces.

**Type identity.** Two families, no exceptions. **Fira Code** (monospace) for *all* display, headings, subheads, labels, and metadata — the precision of a programming font is the brand voice. **Inter** for body and dense UI. Display tracking sits at −3 to −4%; uppercase labels at +8%. Never below 14 px / 0.875 rem for body; never below 24 px on slides.

**Spacing.** 4 px base scale (`--space-1` through `--space-32`). Generous outer padding on cards (24–32 px); tight inner padding for data tables (12–16 px). Air, not noise.

**Layout.** Max content width ~1100–1200 px. Single-column hero, two- or three-up feature grids, four-up stats bands. No asymmetric "designer" grids — Origin's layouts read as orderly columns and rules. Fixed header on scroll, with translucent bone backdrop and `backdrop-filter: blur(8px)`.

**Backgrounds.** Almost always `--color-bone`. Stats bands and dark CTAs flip to `--color-obsidian`. No gradient backgrounds, no full-bleed photography, no patterns. The single permitted "texture" is a 1 px hairline rule (`--color-border` or `--color-border-strong`) used as a structural divider — between sections, in tables, under metadata rows.

**Imagery.** Schematic over photographic. When Origin needs an "image", it shows a **semantic trace** (timestamp · actor · verb · target rows in monospaced columns) rather than a stock illustration. If photographic imagery is ever needed, it is warm-toned, slightly desaturated, and never glossy.

**Borders & dividers.** 1 px hairlines in `--color-border`. `--color-border-strong` for table rules and emphasized separators. No double borders, no inner glows, no gradient borders.

**Corner radii.** Restrained — 6 px on inputs and buttons (`--radius-md`), 10 px on cards (`--radius-lg`), 16 px on hero/CTA cards (`--radius-xl`), pill on tags. Nothing rounder than pill; nothing harder than 2 px.

**Shadows.** Warm-tinted (`rgba(26, 22, 20, 0.06)` base), low-key, two-layer. Cards float subtly (`--shadow-sm` to `--shadow-md`); modals lift higher (`--shadow-lg` to `--shadow-xl`). Never hard drop-shadows, never coloured shadows.

**Animation.** Sparing. Standard easings: `cubic-bezier(0.22, 0.61, 0.36, 1)` for `--ease-out`, with durations 120/180/260/420 ms. Hover transitions on colour and border only. No bounce, no parallax. The one acceptable "live" motion is a status dot's soft pulse halo (4 px ring fading at 0.18 alpha) for the `Active` state.

**Hover states.** Buttons darken (carbon → obsidian). Secondary buttons strengthen border (`--border` → `--color-carbon`). Ghost buttons fill with `--color-selection`. Links shift their underline colour from `--border-strong` to `--color-carbon`. Table rows take `--color-selection` on hover. Never opacity-only hovers.

**Press states.** No transform-based shrink; the system stays stable under interaction. Pressed = darker fill, same size.

**Focus rings.** 3 px halo at 8% carbon (`box-shadow: 0 0 0 3px rgba(51, 48, 46, 0.08)`) plus a 1 px carbon border. Always visible — Origin is sold to security and compliance teams; accessibility is non-negotiable.

**Transparency & blur.** Used in exactly one place: the sticky header gets `rgba(255, 241, 229, 0.85)` background plus `backdrop-filter: saturate(140%) blur(8px)`. Nowhere else.

**Cards.** Surface fill (`--color-surface`), 1 px hairline border, 10–12 px radius, `--shadow-sm`. An eyebrow label (uppercase Fira Code, +8% tracking, slate or ember) sits at the top, not a heavy header bar.

**Dark mode.** All tokens flip via `[data-theme="dark"]` or `prefers-color-scheme: dark` — but the current system ships *light only*; dark tokens are defined and ready, not previewed.

---

## Iconography

Origin uses **[Lucide](https://lucide.dev)** — chosen for its geometric clarity, 1.5 px constant stroke, and round caps/joins (a softer, tech-forward feel that complements Fira Code's monospaced precision).

**Rules.**
- Stroke weight: 1.5 px constant.
- Corner radius: 2 px for elements ≥ 8 px; 1 px below.
- Joins & caps: round.
- Base grid: 24 × 24 with 1 px internal padding.
- Sizes: **16 px** (dense UI), **24 px** (standard), **32 px** (headers).
- Stroke colour: `--color-carbon` (`#33302E`) by default; `--color-slate` (`#66605C`) for de-emphasised; status colours when icons indicate system state.

**Core UI icon set** (used throughout the dashboard): `activity`, `monitor`, `network`, `settings`, `chevron-right`, `alert-circle`, `shield`, `lock`, `search`, `eye`, `users`, `bell`, `download`, `filter`, `terminal`, `database`, `globe`, `zap`, `bar-chart-2`, `check-circle`, `x-circle`, `clock`, `cpu`, `refresh-cw`.

**In production code**, install `lucide-react` and import per-icon for tree-shaking:
```jsx
import { Monitor, Activity, Settings } from "lucide-react";
<Monitor size={24} color="#33302E" strokeWidth={1.5} />
```

**In throwaway prototypes / static HTML**, fetch from the Lucide CDN:
```html
<img src="https://unpkg.com/lucide-static@latest/icons/activity.svg" width="24" height="24" />
```
This is the approach used in the design-system preview cards and the marketing UI kit (`LucideIcon` component in `ui_kits/marketing/FeatureRow.jsx`).

**No emoji** in product or marketing. **No unicode glyphs as icons** — except the middle dot (·) as a separator in metadata, which is treated as punctuation, not iconography. **No custom SVGs** unless absolutely necessary (the wordmark is the exception).

---

## Caveats & substitutions

- **Fonts** — Fira Code + Inter both load from the Google Fonts CDN. Nothing missing. If you ever need offline/print rendering, fetch the WOFF2s into `/fonts` and swap the `<link>` for a local `@font-face`.
- **No codebase or Figma source** was available. The marketing and internal-comms UI kits are interpretive recreations grounded in the token spec and the copy fragments provided. Treat them as a strong starting reference, not as pixel-faithful copies of a shipped product. If/when source artifacts become available, regenerate.
- **No dashboard UI kit** — the user opted for marketing + internal-comms only. The dashboard *visual vocabulary* (semantic trace rows, stat tiles, status pills, endpoint table) is captured in the preview cards and the marketing hero's `SemanticTrace` component, and can be lifted directly when a dashboard kit is added.
- **Dark mode** — tokens defined, not previewed. Flip via `[data-theme="dark"]`.
