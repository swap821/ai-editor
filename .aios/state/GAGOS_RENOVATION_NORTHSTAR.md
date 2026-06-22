# GAGOS Renovation Design North-Star

> **Status:** Decision-ready design dossier · **Date:** 2026-06-21 · **Branch context:** `feat/living-being-p1`
> **Author:** Lead design director, synthesizing 8 web-research lenses against the internal audit (`SYSTEM_AUDIT_2026-06-21.md`).
> **Scope of authority:** layout, motion, geometry, typography, structure, onboarding, honesty, accessibility — all free to evolve. **Sacred and untouchable:** the PALETTE (void `#030108`, luminous cyan `#7bf5fb`) and existing texture/GLB assets. We **elevate within** the palette; we never replace it.
>
> **Context update (2026-06-21):** the frontend has since been collapsed to ONE official surface — the points-being GAGOS at the clean `/` URL. The classic IDE shell, manufacturing shell, organs dock, forge, and the two-palette/five-name fragmentation are DELETED. Where this dossier references reconciling `?ui=classic` or two palettes, read it as: there is now one palette and one shell, so those items simplify to "keep it coherent."

---

## 1. Design Vision

GAGOS is a living mind you can trust. The renovation does not chase spectacle — it earns belief. We open the front door instantly (a real wordmark, a greeting, three clickable invitations, an honest loading state) before we ever raise the curtain on the 3D being, then we elevate that being to award-level by making its every motion *mean something real*. The whole experience lives inside one sacred constraint — a near-black cosmic void lit by a single luminous cyan — and that constraint is our advantage: the 2026 leaders (Linear, Perplexity, Vercel Geist) have independently converged on exactly this archetype (near-black canvas + one rationed accent). The gap GAGOS must close is not aesthetic, it is **coherence, honesty, and a trust vocabulary**: one name, one token system, no fake numbers, no blank frames, no inaccessible hero. We spend cyan like Linear spends its accent — as a status light that means "real, live, actionable" — and we let luminance, rhythm, and scale (never new hues) carry the being's entire state machine. Front-door first; then we make the voyaging mind breathe like the most beautiful object on the web.

---

## 2. Named Design Principles

1. **Open the door in <100ms.** The first frame is never blank, never a fake spinner, never gated on shader compile. A real DOM/poster baseline (wordmark + greeting + starter prompts) paints instantly; the being fades in *over* it. (Pattern: GitHub Globe inline-SVG→canvas crossfade; 14islands progressive enhancement.)
2. **The being speaks first.** The empty chat is replaced by a warm greeting and 3-4 clickable starter prompts that teach capability — onboarding *is* the product, no modal tour. (Perplexity / Gemini zero-state.)
3. **Cyan is a status light, not paint.** Ration `#7bf5fb` to exactly one earned signal per view: the live/alive cue, the single primary action, and verified/real markers. Everything else is the neutral void ramp. (Linear `#e4f222` discipline; Geist accent restraint.)
4. **Truth or honest absence — never fake precision.** Every status surface is one of three states: live (real backend value), loading (skeleton, not zeros), or offline/error (plain-language cause + recovery). No fabricated number is ever styled as real. (PRODUCT.md "data must be true"; the audit's `18.23 GB` / `2,605 nodes` violation.)
5. **State is luminance, not new color.** Connection, freshness, and confidence ride cyan luminance + saturation and motion rhythm — live = full-luminance pulse, stale = desaturated/dimmed, offline = near-monochrome — so honest state never breaks the sacred palette.
6. **One mind, one name, one token source.** Everything is **GAGOS**, and every color/space/radius/type/duration routes through one semantic token layer.
7. **Two motion registers, kept apart.** Chrome motion is fast, functional confirmation (sub-250ms, GPU-only, ease-out); being motion is slow, organic, alive (spring physics, breathing envelopes). Never flatten the creature into mechanical UI tweens, never let the UI feel sluggish.
8. **The meaning survives without the GPU.** A real `<h1>` wordmark, a screen-reader live description of the being's state, keyboard-operable proxies, 44px targets, a 2D poster fallback, and a true reduced-motion still-pose. The 3D is an enhancement, never a barrier.
9. **Additive and port-safe.** All product work lands in product-safe files (`SuperbrainApp.jsx` mounts, new overlay components, `index.html`, token layer) that survive `npm run port`. The ported 3D tree (`superbrain/*`, `GagosChrome`) is authored in the lab and synced — product edits never fight the overwrite.
10. **Restraint reads as intelligence.** No bloom-everywhere, no particle confetti, no glassmorphic AI-slop. Drama is reserved for the being's life; the chrome stays calm. Spectacle-as-intelligence erodes trust.

---

## 3. Design System Direction (concrete values, within the sacred palette)

### 3.1 Color, elevation & glow — a 3-input perceptual engine
Fix two values, expose one knob. **base = `#030108` (void)**, **accent = `#7bf5fb` (cyan)**, plus a single **contrast** control (Linear's 3-variable model, down from ~98 vars). Derive everything in **OKLCH/LCH** so steps are perceptually even and the void stays the void.

- **Surface ramp (lightness steps on the void, ~0 chroma, never new hues):**
  `--surface-canvas: #030108` → `--surface-1: #07050E` → `--surface-2: #0C0916` → `--surface-3: #12101F` (modals/popovers). ~+3-4% L per step, whole stack inside a ~5-step range (Linear/Raycast/Material doctrine: depth = lightness, **never shadow** on near-black).
- **Elevation mechanic:** translucent-white overlays (`rgba(255,255,255,0.03 / 0.05 / 0.08)`) + a **1px inset hairline** (`--border-subtle: rgba(255,255,255,0.10)`), not drop shadows. Reserve one soft, void/cyan-tinted shadow only for the topmost floating layer.
- **Neutral text ramp (off-white, never pure `#FFFFFF` — it halates on the void):** `--text-primary: #E8E6EE` (≥4.5:1 on every surface step) · `--text-secondary: #9A96A6` · `--text-disabled: #5E6671`.
- **Accent ramp (seeded from `#7bf5fb` in OKLCH):** `--accent: #7bf5fb` · `--accent-hover` (+~8 L) · `--accent-muted` (lower chroma, secondary affordances) · `--accent-hot: #C9FBFE` (hottest highlight core). Contrast rule (Stripe "levels apart"): ≥5 ramp steps apart = 4.5:1 (text); ≥4 = 3:1 (large/non-text).
- **Glow discipline (the being):** switch tone mapping from `ACESFilmic` → **AgX** (or Khronos PBR Neutral) so saturated cyan rolls off to a hot near-white *core* instead of hue-shifting/clipping to flat white; `toneMappingExposure ≈ 0.8–1.1`; **threshold-gated UnrealBloom** so only the brightest tips/active nodes/crown bloom — glow becomes a meaningful "alive/active" signal, not an everywhere-haze. (Reference: three.js tone-mapping overview.)
- **Text legibility over the living shader:** a same-color void scrim `rgba(3,1,8,0.35–0.45)` behind any reading text; never place text over the noisiest shader region (palette-neutral because the scrim *is* the void).

### 3.2 Type scale — weight & tracking carry hierarchy
One variable grotesk for UI/HUD (**Inter / Inter Display** class) + one mono for identifiers/numerals (**JetBrains/Geist/Berkeley Mono**, `tabular-nums` so live data never jitters). Optional refined display/serif only for the being's "voice"/welcome. Major-Third (1.25) in `rem`:

| Token | Size | Weight | Tracking | Line-height |
|---|---|---|---|---|
| `--text-display` | 48px | 600 | −2.4px | 1.05 |
| `--text-h1` | 31px | 590 | −1.2px | 1.15 |
| `--text-h2` | 25px | 510 | −0.6px | 1.2 |
| `--text-body` | 16px | 400 | +0.1px* | 1.6 |
| `--text-sm` | 14px | 400 | +0.2px* | 1.5 |
| `--text-caption` | 12px | 400 | +0.3px* | 1.4 |
| `--text-micro` | 11px (mono) | 500 | +0.4px* | 1.3 |

*Slightly **positive** tracking at small sizes adds air on the dark void (Raycast trick). Use weights **400–600**, never 300 (thin type goes spindly on near-black). Linear's 510/590 discipline = "precise, not loud." Inputs ≥16px (stops iOS auto-zoom). The currently `aria-hidden` hero gets a real on-screen + screen-reader `<h1>` GAGOS.

### 3.3 Spacing & radii
Strict 4/8 grid — `2 / 4 / 8 / 12 / 16 / 24 / 32px` tokens + a **96–128px section rhythm** between major blocks. No one-off magic numbers (kills the current `13px` / `38px` "demo" feel faster than any visual change). Lock **one** radius scale: `2 / 4 / 6 / 8 / 12 / 16 / 9999`; pills (`9999`) reserved for tags/badges only.

### 3.4 Motion language — two registers, tokenized
- **Chrome motion (fast, functional):** durations `--dur-quick: 0.1s · --dur-regular: 0.2s · --dur-slow: 0.35s`; ease-out entrances (`cubic-bezier(0.23,1,0.32,1)` / expo `(0.19,1,0.22,1)`); exits ~20% faster than entrances; **transform/opacity/color only** (never `width/height/top/left` or `transition: all`); `scale(0.97)` ~150ms on `:active`; origin-referenced; 30–50ms stagger on group reveals, clamped to ~400ms total.
- **Being motion (slow, organic):** **spring-first**, not duration-first (Apple two-knob: `response 0.3 / damping 0.8` for routine settles; `0.2 / 0.55` for rare "aha"). Idle = layered breathing: low-freq body sway + high-freq surface flutter + a slow "gust" amplitude envelope giving a **4–6s breath** (12–15 breaths/min), vertex/luminance drift from in-shader 3D simplex noise. 1:1 pointer tracking + release-velocity handoff + full interruptibility.
- **Reduced-motion contract:** collapse all chrome motion to ~150ms opacity-only; **freeze the breathing envelope to a static luminous low-glow resting pose** (the being stays *present*, just still); disable parallax/camera-drift/turbulence; switch idle to `frameloop='demand'`. Honor BOTH the OS query AND a persistent in-UI "Calm" toggle.

---

## 4. Front-Door Blueprint (FIRST)

**Goal: in the first 5 seconds, answer "what is this?" with one confident name, one beautiful frame, and one obvious first move — accessibly, honestly, on any device.**

1. **Instant DOM baseline + crossfade reveal.** `index.html` already paints a breathing cyan boot mark and dispatches/listens for `gagos:ready` — extend it into the real front door: an inline CSS void (`radial-gradient` from `#030108` with a faint `#7bf5fb` core glow) + a real `<h1>GAGOS` + one-line value prop + 3-4 starter-prompt cards as **real DOM**. Compile shaders async (`renderer.compileAsync()` / `KHR_parallel_shader_compile`); when resolved, crossfade poster→canvas over ~400–600ms. The DOM baseline is what screen readers and no-WebGL clients get.
2. **Resurrect the dead boot cinematic.** Wire `BootSequence.tsx` (currently never rendered) to the `gagos:ready`/compile-resolve event so it finally plays — as the *honest* warm-up window, sequenced as progressive disclosure: beat 1 materialize the resting being + greeting; beat 2 teach the one core gesture; beat 3 hand over control ("Go ahead — talk to it"). Event-driven not timer-driven.
3. **The being speaks first.** Empty chat → warm zero-state at the brainstem: heading ("I'm GAGOS — a supervised mind that remembers") + 3-4 capability cards as **real ≥44px `<button>`s** (`build a landing page` · `audit my security gates` · `what do you remember about this project?`). Click **pre-fills** the input (never auto-sends — preserve agency); cap at 4.
4. **One honest EmptyState primitive** (icon → Title-Case title → sentence-case description → ≤1 primary +1 optional secondary, **real** Button/Link, Verb+Noun labels) for five variants: blank-slate, no-results, cleared, offline/permission, error (error carries a copyable request ID + "Try Again").
5. **One name, one token layer.** GAGOS in `<title>`, meta/OG, boot, chat persona, error copy, `aria-label`, manifest, skip link. Ship one CSS-custom-property token file (§3) consumed by the chrome.
6. **Honest loading ladder:** <1s nothing · 1–2s structure-mirroring skeleton (slow cyan shimmer, reduced-motion gated) · 2–10s determinate step labels ("Compiling shaders → Connecting to backend → Loading memory") · 10s+ notify-when-done. Unknown metric → shimmer `—`, never a fabricated number. Boot "facts" call `/health`; on failure show **"backend offline"**.
7. **Responsive home.** Add breakpoints (`640 / 1024 / 1440`); the chat is currently hardcoded `min(430px, 40vw)` absolutely positioned with **zero breakpoints** — on narrow screens stack the chat **below** the being, reflow starter cards, ship a smaller mobile asset tier, pause RAF / `frameloop='demand'` when hidden.

---

## 5. Elevation Blueprint — the 3D Being (THEN)

**Goal: take the already-built voyaging mind to award-level, entirely within the sacred palette, by making every motion mean a real event.**

1. **Presence state-machine wired to real backend events.** Expressed *only* through breathing rate, scale, particle velocity, and cyan luminance — never new color: **RESTING** ~5s breath, ~40% glow · **LISTENING** ~2.5s breath, ~70% glow, gentle inward gather · **THINKING** ~0.8s pulse + rising noise turbulence · **SPEAKING/STREAMING** luminance modulated by token-arrival rate · **OFFLINE/ERROR** breath slows, dims to ~20%, cools. Reasoning streams as nerve-pulses; tool-calls light distinct nerve tips. **Never animate activity not backed by a real event.**
2. **Spring physics for all core motions** (wake, tab materialization from the vertebra, focus-tab scale/position, chat-box appearance): critically-damped springs, ≤~300ms perceived travel, origin-referenced, interruptible. Decouple idle-breathing from interaction springs.
3. **"Fake the expensive thing" rendering** (Lusion): matcaps + baked normal/AO/thickness maps + analytical/faked volumetric glow instead of real dynamic lights+shadows; bake organic motion as keyframe-reduced 16-bit Vertex Animation Textures.
4. **Runtime quality ladder.** Clamp DPR to `[1,2]`; `PerformanceMonitor` downgrades at ~45fps (DPR→1 → disable post-FX → thin particle/nerve counts); instance the nerve lattice / spine vertebrae / tabs into `InstancedMesh`/`BatchedMesh` (<~100 draw calls / 16.67ms budget; ≤3 active lights). Idle brain runs `frameloop='demand'`.
5. **Per-claim provenance** (Perplexity): any memory/retrieved assertion gets an inline cyan citation chip at the claim, expandable to source + "updated N ago"; stale provenance desaturates.
6. **Preview-before-act + reversible diff + undo** (the supervised-AI-OS trust contract): plan card on the being's anatomy before any backend write, before→after diff on confirm, ~10s undo toast, rollbackable checkpoints. Optimistic UI with **visible reconciliation**.
7. **Future-proof shaders in TSL** → WebGPU-first with automatic WebGL2 fallback (`await renderer.init()`), WebGPU compute reserved for the nerve/particle field. Browser-native, no Unreal.

---

## 6. Honesty, Accessibility & Responsive Standards

**Honesty:** three states per data surface (live / loading-skeleton / offline-error-with-recovery); one true "is GAGOS okay?" HUD signal answerable in ~2s; every number carries an "as of" timestamp; name the silent CORS `Failed to fetch` trap as a plain-language recoverable state; calibrated confidence over false certainty; graceful "I don't know" as first-class.

**Accessibility:** replace `aria-hidden` on the hero with `role="img"` + a **dynamic** `aria-label` narrating state via polite `aria-live`; synchronized invisible DOM proxy layer over every interactive 3D element (real `<button>`/`<a>` + `tabindex=0`, Enter/Space activation), position-synced each frame; never paint reading text into the canvas; `:focus-visible` 2px `#7bf5fb` ring, `outline-offset: 2px`; all targets ≥24px (AA) / **≥44px touch** (fix the current 38px mic/send); visible-on-focus "Skip the visualization → go to chat" as the first focusable element; nothing flashes >3×/sec.

**Responsive:** breakpoints `640 / 1024 / 1440`; stack chat below the being on narrow screens; mobile asset tier; pause RAF when hidden; no focus traps on small screens.

---

## 7. Phased Renovation Roadmap

Front-door first (Phase 1–2), then elevation (Phase 3), then future-proofing (Phase 4). Effort: **S** ≤ a day · **M** a few days · **L** a week+. All product work in product-safe / port-surviving files; ported-tree edits (3D scene) authored in the lab + `npm run port`.

### Phase 1 — Coherence & the Open Door *(highest leverage, lowest risk)*
- One name "GAGOS" everywhere (title, meta, persona, errors, aria, manifest) — **S** *(partially done 2026-06-21: title/meta/noscript)*
- Single OKLCH semantic token layer (void+cyan+contrast) — **M**
- Extend `index.html` boot loader into the real instant DOM front door (wordmark + greeting + starter cards + void poster) — **S**
- Kill the blank first frame: `compileAsync` warm-up + poster→canvas crossfade; dispatch `gagos:ready` from the scene arrival handler (lab + `npm run port`) — **M**
- Honesty pass: replace fictional boot numbers with `/health`-bound state or honest absence; three-state data surfaces — **M**

### Phase 2 — The Front Door Works for Everyone *(onboarding, honesty, a11y, responsive)*
- The being speaks first: product-safe `WelcomeOverlay` (greeting + 3-4 ≥44px starter prompts that pre-fill chat, never auto-send; `localStorage`-gated) — **S**
- One EmptyState primitive × 5 variants — **M**
- Resurrect `BootSequence.tsx` as event-driven cinematic / progressive-disclosure first-run — **M**
- Accessible hero: `role="img"` + dynamic `aria-label` + aria-live; DOM proxy layer; skip link; 44px targets; `:focus-visible` cyan ring — **L**
- True reduced-motion contract (OS query + in-UI Calm toggle; still resting pose) — **M**
- Responsive home: breakpoints, stack-on-narrow, mobile asset tier, pause-RAF-when-hidden — **M**

### Phase 3 — Elevate the Being to Award-Level *(within palette)*
- Presence state-machine wired to real backend stream events (luminance/rhythm only) — **L**
- Spring-physics motion system + layered breathing envelope; formalize waiting-tab idle-bob — **M**
- Tone-mapping ACES→AgX + threshold-gated bloom; matcap/baked-map pass — **M**
- Runtime quality ladder + instancing (<100 draw calls, DPR clamp, adaptive downgrade) — **M**
- Per-claim provenance chips on memory/retrieved assertions — **M**
- Preview-before-act + before→after diff + undo + checkpoints; optimistic UI with visible reconciliation — **L**

### Phase 4 — Future-Proof *(browser-native, no Unreal)*
- Author shaders in TSL; WebGPU-first with automatic WebGL2 fallback; WebGPU compute for nerve/particle field — **L**

---

*Sacred palette preserved throughout — every elevation derives from `#030108` + `#7bf5fb`. Front-door first, then the mind breathes.*
