# HUD REFERENCE LANGUAGE — the GAGOS Superbrain world, as design law

> The north-star spec the 2D HUD overlay must HARMONIZE WITH. The 3D scene is
> SACRED and READ-ONLY — this document only describes it so the renovated HUD
> reads as the same hand, the same depth, the same world. The HUD is the
> **instrument**; the brain supplies the color. Every value below is cited from
> the actual scene/token source (file:concept).
>
> Theme (operator's canon): *"an autonomous AI-OS superbrain travelling constant
> into the deep-vast knowledgeable infinite space."* WORKING + MOVING FORWARD are
> the two soul verbs; the HUD must express both with REAL data, never decoration.

Source files: `SuperbrainScene.tsx`, `CosmicBackground.tsx`, `KnowledgeHorizon.tsx`,
`MemoryGalaxy.tsx`, `AccretionCore.tsx`, `NeuralAura.tsx`, `OrganSurface.tsx`,
`CorticalSignals.tsx`, `NervousSystem.tsx`, `CognitiveGrasp.tsx`, `PostFX.tsx`,
`TierGovernor.tsx`, `superbrain.css` (`:root`), `lib/constants.ts` (`POST_FX`).

---

## 1. PALETTE & LIGHT — color is LIGHT, not paint

The void is near-black (`--bg: #010307`, scene `background #000000`). ~80% of the
sky sits below 0.04 luminance (`KnowledgeHorizon`: "80% of sky < 0.04"). Color
exists only as emission against that black, on a strict **luminance ladder**
(`SuperbrainScene` cortex header): base 0.08 → core glow ~0.18 → SSS ~0.3 → fresnel
rim 1.2–1.6 → filaments/wavefronts ~2.2 (the only hot pixels). The bloom knee is
`smoothstep(1.0, 1.9, luma)` (`POST_FX.bloom` threshold 1.0): **anything ≤ ~0.5
stays dark and never blooms; only filaments/stars sparkle.**

**The brain's own anatomical spectrum** (full color lives HERE, not in the HUD):
- Frontal red-orange `#ff3b28` → `#ff7a26`
- Parietal crown electric cyan `#19d4f0`
- Temporal green `#36f07a` → lime `#a8e62b`
- Occipital violet `#9b3bff` → magenta `#e62bd4`
- Cerebellum deep violet `#6a35ff`

**Mode-reactive core tint** (eased, never snapped): observe `#10164a`, synthesize
`#35205f`, orchestrate `#5c183d` (`MODE_EMISSIVE`). Aura spark temperature shifts
with mode: observe cyan `#40e8ff`, synthesize whiter `#aef2ff`, orchestrate violet
`#8f7bff` (`AURA_MODE_COLORS`).

**Light sources & grade.** Cool key/fill rig: directional `#8fa8ff`/`#bcd0ff`/
`#795cff`, point lights `#5e8dff`/`#c8a8ff`/`#ff5c9a`, ambient `#241145` @0.14.
A virtual **rose backlight behind the brain** slowly orbits ±15° (`uBackLightDir`).
AgX tonemap (exposure 1.45), then a teal-shadow / amber-highlight split-tone
(`POST_FX.grade`: shadowTint `[0.42,0.52,0.55]`, highTint `[0.52,0.5,0.44]`,
vibrance 0.21) — **shadows lean teal, highlights lean amber/gold; true black is
preserved** (soft-light keeps `softLight(0,s)=0`). Stars are blackbody-tinted
(~75% near-white, ~15% warm, ~10% blue), saturation < 0.25, **never pure white
(AgX clips it to paper)**.

### THE ONE-ACCENT RULE (the HUD's binding law)
`superbrain.css` `:root` declares **one accent: `--accent: #5ce1e6` (cyan)**, used
ONLY for: the status dot, the Execute button, the active mode item (+ a brief
acquisition flash + sparklines at reduced opacity). **Everything else is neutral**:
`--text-1 rgba(232,238,250,.92)` / `--text-2 rgba(160,170,190,.6)` /
`--text-3 rgba(120,130,150,.38)`, hairlines `rgba(255,255,255,.08)`. Two reserved
**state** hues only (semantics, never decoration): ok-green `#58d68d`/`#34d399`,
busy/hold-amber `#e0a84f`/`#ffb454`, tamper-red `#ff5c5c`. **HUD law: hovers
brighten toward white-alpha, NEVER toward a hue.** The HUD never borrows the
brain's rainbow as chrome — the brain wears the color; the HUD stays glass + cyan.

---

## 2. DEPTH & SPACE — the "deep-vast infinite" feeling

The scene builds depth with **stacked layers at honest Z**, not faked perspective:
- **Sky dome** (`KnowledgeHorizon`) radius 90, `renderOrder -2`, BackSide — IQ
  domain-warped Hubble-SHO nebula (near-black → teal → amber-gold → near-white),
  ridged filaments, **dark dust lanes that OCCLUDE gas + stars** ("occlusion =
  strongest depth cue"). One soft diagonal galactic band lower-left→upper-right
  *behind* the brain; star density 4× in-band, corners near-empty. View-center is
  deliberately calmed — "the brain owns that real estate."
- **Three-layer differential pointer parallax**: far 0.02 / mid 0.06 / near 0.14
  (`KnowledgeHorizon` `par`) — closer layers shift more = parallax depth.
- **Starfield as KNOWLEDGE** (`CosmicBackground`): 4500/2500/1200 by tier, glyph
  atlas (∑ ∆ ∞ ∫ π Ω, code, numerals) — the stars are literally
  knowledge-symbols streaming toward camera, scaling up "coming close becoming
  big," then **grasped & dissolved into the core** within 25 units.
- **Memory galaxy** (`MemoryGalaxy`): every REAL trail a persistent star orbiting
  the mind (radius 7.5–13), brightness=strength, size=walks, deterministic
  placement so a skill keeps ITS place across sessions.
- **Scale anchor**: brain `BRAIN_SCALE 3.02`, hero camera dollied OUT to z=7.5
  ("soothing size"). Atmosphere vignette + radial darkening (`.atmosphere-layer`,
  `POST_FX.vignette` offset 0.28 / darkness 0.62) pulls the eye to center.

**How a 2D panel echoes depth without faking 3D:** lift via the *light-from-above*
rim (visionOS), inner top-highlight + bottom inner-shadow, and a big soft cast
shadow — the canon glass stack: `inset 0 1px 0 rgba(255,255,255,.1)`,
`inset 0 -14px 28px -18px rgba(0,0,0,.5)`, `0 24px 70px rgba(0,0,0,.45)`. Let the
scene's color bleed THROUGH the glass (`saturate(140%) brightness(1.08)`) so panes
feel suspended IN the nebula, not pasted on it. Use occlusion + scrims
(`.bottom-scrim`, faint `.grid-layer` masked radially at 0.065 opacity) for the
same "things in front of things" cue the dust lanes give.

---

## 3. MOTION CADENCE — calm but alive; motion only when it means something

**The voyage (MOVING FORWARD) is non-negotiable.** Convention: the brain travels
toward **-Z**; the knowledge field flows past toward +Z (`SuperbrainScene` travel
comment; `CosmicBackground` `transformed.z += uTime*speed`, wraps over range 140).
A perpetual **dolly wave ~0.04 Hz** keeps the camera breathing along travel
(`CameraDrift dollyWave`); slow **60s orbit** (`time*0.015`); the ship **banks into
turns** (`BANK_GAIN 0.633`) with a constant **forward lean 0.05**.

**The breath (WORKING/alive).** Asymmetric layered systole, NOT a 1 Hz pulse
(`SuperbrainScene` useFrame): systole `pow(...sin(time*0.628)...,1.8)` (~0.1 Hz) +
swell (0.043 Hz) + tide (0.017 Hz), weighted 0.62/0.26/0.12. Rim gain ±15%, SSS
±20%. Cortex rim pulse `sin(uTime*2.0)`. **The whole organism breathes on ONE
shared uniform** so cortex/aura/signals/wires move as one body.

**Pulses & surges (event-driven only):** cortical thought-waves at Poisson 3–8s
*and* on real tool dispatch (front 1.4 u/s, decay 0.8/s, `THOUGHT_WAVE_GLSL`);
synapse fireflies blink `pow(...,8.0)` — a sharp spike, not a lava lamp; nerve
data-packets flow along the wires; cognition burst → camera shake + dolly-in,
decaying ~2s. **Idle attract-mode** after 30s: extra yaw 0.02 rad/s eased in over
2.5s, ±2° pitch, eased out in 0.6s on any input.

**The HUD must share this exact cadence** (`superbrain.css` `:root` motion tokens —
"every transition/animation rides on these"):
- `--ease-out-expo cubic-bezier(.16,1,.3,1)` — entrances, **600–900ms** (boot:
  650ms, staggered 0/120/260/420/560ms).
- `--ease-out-quart cubic-bezier(.25,1,.5,1)` — hovers/state, **200–300ms**.
- `--ease-in-soft cubic-bezier(.55,0,1,.45)` — exits / line-dim.
- `--ease-loop cubic-bezier(.42,0,.58,1)` — ambient loops (status `breathe 2.2s`,
  scanline 9s, wire-glow 3s).

**Discipline:** motion only when it carries meaning (a real packet lands, a state
truly changed). No idle wiggle for its own sake. **Never animate paint
(box-shadow/border/background) on a backdrop-filtered element** — it forces a
per-frame re-blur (the file documents ~9 FPS regressions). Animate transforms/
opacity, or toggle a STATIC gradient via a CSS variable (e.g. `--rim-top`
0.16→0.24 on focus). Honor `prefers-reduced-motion`.

---

## 4. MATERIALITY — the exact glass recipe the HUD must reuse

**Glass** (`.glass-surface`, `.command-bar`, `.approval-panel`): bg
`rgba(11,14,20,0.5)` (panels) / `rgba(6,9,22,0.74)` (command bar), radius 14–16px,
`backdrop-filter: blur(14px) saturate(140%) brightness(1.08)` (saturate capped
~140% so near-black scenes don't milk out), the 3-part shadow stack from §2.

**Edge-lit rim** (replaces a flat border): a 1px masked gradient frame, top stop
`rgba(255,255,255,var(--rim-top))` → 0.055 @20% → 0.035 @62% → 0.07 @100%, masked
with `mask-composite: exclude`. Focus brightens the variable, never the paint.

**Grain (always static, never animated):** per-pane `.glass-grain` opacity 0.04
`mix-blend-mode: overlay` + full-frame `.frame-grain` (z 40) — one shared optical
film over canvas + DOM, matching the scene's own `POST_FX.noise` 0.025 +
interleaved-gradient-noise dither (±1/255) that every shader uses to kill banding.

**Specular consistency:** one light direction everywhere — `inset 0 1px 0
rgba(255,255,255,.08)` on every raised chip/avatar/mode-num (light from above,
same as the brain's rim).

**Accent surface** (Execute, the rare hue): bg `--accent`, text `#04181a`,
`inset 0 1px 0 rgba(255,255,255,.35)` + `0 6px 22px rgba(92,225,230,.22)`; hover
adds a transform-only scaleX sweep (never a background animation).

---

## 5. THE TWO SOUL VERBS, ALREADY VISUAL (bind HUD to the SAME real channels)

**WORKING** — the mind is active with real signals:
- Each dispatched tool fires a **thought-wave at the lobe that owns that work**
  (`waveLabelForTool`: plan/recall→CAUSAL frontal, read/search→ARCHIVE temporal,
  write/exec→LATTICE crown, else SIGNAL occipital). Same anatomy the region pins
  use → one number, every surface (`.region-pin` bound to the same metricsStore).
- Verifier GREEN / SKILL MASTERED → **synapse storm** (all anchors fire, camera
  surge 1.0). Approval-required → **the hold**: breath freezes, organism turns
  amber `#b96a14`/`#ffb454`, wires dim to 0.3, **the voyage itself slows to ~30%
  clock** (`CosmicBackground` holdRef). The HUD already mirrors this: command bar
  `.is-approval-hold` amber, approval panel amber-framed, the diff IS the content.
- Accretion disc = "the stomach": glows ~1.2s when a knowledge packet is absorbed.
- Memory stars flash on real reinforcement/recall; quarantine = pulsing red.

**MOVING FORWARD** — the constant voyage (§3). The HUD expresses forward motion
through *settling* entrances (translateY 14px → 0 on expo) and live readouts that
advance, not through gratuitous drift. The status dot `breathe`s; the active-brain
dot encodes privacy truth (local green vs cloud amber). **HUD law: every live
indicator reflects computed reality** (link-down amber, tamper red, fidelity tier)
— honest dormancy when there's no data (galaxy/grasp return null with zero trails).

---

## 6. THE "CLEAN DEEP THINKING" QUALITY (the anti-slop discipline)

What makes it restrained, considered, calm-yet-alive — and what the HUD must NOT do:
- **Restraint of color.** One accent. The void stays void. No gradient soup, no
  neon chrome. Color is earned emission tied to anatomy/state, never garnish.
- **Restraint of motion.** Slow cadences (orbits in minutes, breath in ~10s
  cycles). Motion is meaning. No bouncing, no spinners-for-spinners, no idle
  jitter. Reduced-motion fully honored.
- **Restraint of brightness.** A strict luminance ladder with 2× bloom headroom;
  nothing clips; highlights roll off (AgX). Faint filaments over blunt glows.
- **Determinism & honesty.** Seeded randomness everywhere (identical field each
  mount, honest screenshots). Numbers are REAL (trails, verifier passes); nothing
  is invented; dormant when truthfully empty.
- **Type discipline.** Display (`Outfit`) only for the ONE hero title; mono
  (`JetBrains Mono`) for data/eyebrows/timestamps; Inter for body. Tabular-nums on
  every changing figure so nothing reflows. Tight tracking on values, 0.12em on
  labels. All-caps only for the eyebrow role.
- **Performance as fidelity.** No paint animation on blurred glass; demote-only,
  operator-owned (FIDELITY is sacred — never auto-degrade).

The HUD must NOT: bolt a dashboard over the brain; introduce a second accent or
borrow lobe colors as chrome; animate to fill silence; clip/bloom; fabricate data;
use drop-shadowy card stacks that ignore the single light direction; or break the
voyage.

---

## 7. JUDGING RUBRIC — does this HUD panel belong to THIS world? (yes/no)

1. **One accent?** Only `#5ce1e6` carries hue (status dot / Execute / active
   mode). Everything else neutral; hovers go white-alpha, never a hue. (Y/N)
2. **Canon glass?** Reuses `blur(14px) saturate(140%) brightness(1.08)` + the
   3-part shadow + edge-lit rim + static grain — scene color bleeds through. (Y/N)
3. **Shared cadence?** All transitions ride the four `:root` easing tokens at the
   declared durations (entrances 600–900ms expo, hovers 200–300ms quart). (Y/N)
4. **Calm but alive?** Motion only on real events/state; no idle wiggle;
   reduced-motion respected. (Y/N)
5. **No paint-on-blur?** No animated box-shadow/border/background on any
   backdrop-filtered element (transforms/opacity/var-toggle only). (Y/N)
6. **Both soul verbs, with real data?** Reads as WORKING (live signals/anatomy-
   bound metrics, the amber hold) AND part of the forward VOYAGE; never fakes it,
   shows honest dormancy when empty. (Y/N)
7. **Depth, not flat?** Light-from-above rim + cast shadow + scene-bleed make it
   sit IN the deep-space world, not pasted over it; doesn't crowd view-center. (Y/N)
8. **Type & numbers disciplined?** Display only for the hero; mono for data;
   tabular-nums on changing figures; one all-caps role (eyebrow). (Y/N)

A panel that can't answer **yes to all 8** does not yet belong to the superbrain's
clean deep-thinking world.
