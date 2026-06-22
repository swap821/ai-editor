# RENOVATED HUD BUILD SPEC — honest soul-embodiment + anti-slop purge

> Build target: the 2D HUD overlay only (`SuperbrainHUD.tsx` + lab `globals.css`), lab-first then `npm run port`.
> The 3D brain + cosmic space are the REFERENCE (see [[HUD_REFERENCE_LANGUAGE]]); FROZEN, never touched.
> Every panel must answer YES to all 8 checks of the 'belongs to this world' rubric (reference doc section 7).
>
> **This is a PURGE, not additive theatre.** The previous draft of this spec narrated a soul but
> left the slop in place and even cited undefined CSS vars. This revision DELETES the fakery first,
> then wires the few honest signals the soul actually needs. Net token count should go DOWN, not up.

---

## 0. Why this was rewritten (the anti-slop verdict)

The renovation's thesis is right: *"rest is not death; nothing in the HUD moves unless a real backend
signal moved it; the HUD is the brain's honest instrument readout."* But the prior draft violated its own
thesis. It kept the decorative motion, kept a fabricated progress formula, kept fake lore, invented a
build-version stamp, sprinkled em-dashes, and referenced **CSS variables that do not exist** (`--pass`,
`--earned`). A soul that is narrated but not made HONEST is just more slop with better copy.

So the rule for this build is blunt: **if a pixel cannot point to a real backend value or a real bus event,
it is removed — not restyled, not re-captioned, removed.** Honest dormancy (zeros, dashes, baseline
hairlines) is the correct idle state. The brain owns the color and the motion; the HUD stays glass + one
cyan + real numbers.

### 0.1 Ground truth verified against the real lab tree (every claim below is checked)

| Fact | Where (verified) | Consequence |
|---|---|---|
| Lab is authoritative | `GAG demo/gag-orchestrator/src/` | Edit here only. `frontend/src/superbrain/*` is port output, NEVER hand-edited. |
| CSS is generated | `port-to-frontend.mjs` regenerates product `superbrain.css` from lab `src/app/globals.css` | You edit **lab `src/app/globals.css`**. The product `superbrain.css` is a build artifact. |
| HUD component | lab `src/components/ui/SuperbrainHUD.tsx` (byte-identical to the product copy) | Single file; all panels + the portal live here. |
| **Cognition bus has only these event types** | `src/lib/cognitionBus.ts:13-36` | `knowledge-acquired`, `directive`, `burst`, `agent-dispatch`, `synthesis`, `approval-required`, `approval-resolved`, `telemetry`, `route`. **There is NO `recall`, `model-text`/`generation`, or `tool-dispatch` event.** The live phase MUST be derived from these existing events (see §2). Inventing new event names is fabrication. |
| `generating` is real | `useQualityTier()` -> `generating` (consumed at `SuperbrainHUD.tsx:586,642,945`) | A true "model is producing" flag; drives SYNTHESIZE. |
| `--accent #5ce1e6` is the only accent | `globals.css:16` (+ the one-accent comment `globals.css:4-8`) | One accent, enforced. |
| `--state-ok #58d68d` is **already canon** | `globals.css:17`, used `globals.css:1149` | Sanctioned status green for the link/privacy dots. The one-accent audit MUST account for it: it is **state, not a second accent**, so it is not a violation. |
| `--state-busy #e0a84f` is **already canon** | `globals.css:18`, used `globals.css:1153` | Sanctioned busy/hold/fail amber. |
| `--pass` and `--earned` **do not exist** | absent from `globals.css` (grep clean) | The prior spec referenced them — that is the undefined-var defect. They are **deleted from the spec**; the terminal verdict/delta use `var(--accent)` and `var(--state-busy)` (see §6). |
| tamper-red `#ff5c5c` exists as a literal | `globals.css:576` | Reserved state hue (audit-chain break). |
| The HUD portal is FLAT 2D | `createPortal(... , document.getElementById('hud-portal-root'))` at `SuperbrainHUD.tsx:1083`; `#hud-portal-root` is a plain `<div>` created in `components/canvas/WorkspaceCanvas.tsx:254` | The portal subtree (topbar, core-readout, terminal, command bar) is flat DOM, not in the scene graph. **Any new center overlay mounts HERE.** |
| The left + right consoles are SCENE-PINNED | `<Html position={[-4.8,-1.7,0]}>` (`:1093`) and `<Html position={[4.8,-1.5,0]}>` (`:1144`) | These pin to 3D coordinates. A pheromone overlay must **never** be a new `<Html position>` console — that would breach the frozen 3D-scene interaction contract (steals brain orbit/drag, re-projects each frame). |
| Canvas-freeze list | `port-to-frontend.mjs:27-41` (the live-set manifest) | The diff must touch ONLY `SuperbrainHUD.tsx` + `globals.css` (+ lab tests). |

**One correction the builder must honor:** every "edit superbrain.css" in any older note is shorthand for
**lab `src/app/globals.css`**. The product CSS updates only via `npm run port`.

---

## 1. Unifying thesis (unchanged in spirit, enforced in fact)

The HUD is the superbrain's **honest instrument readout** of its own real work and forward voyage. Read top
to bottom it tells ONE continuous, TRUE story:

- **Topbar** — vital signs: link, live latency, the active brain, the audit shield. Real readouts only.
- **Mode rail (left console)** — the brain's CURRENT live phase, derived from the real turn (OBSERVE /
  SYNTHESIZE / ORCHESTRATE), with honest REST when idle. Not an operator toggle, not a static map.
- **Left "ACTIVE COGNITION" console** — the cadence of real dispatch: phase, tools this turn, real elapsed,
  the heartbeat that fires only on a real tool, the breadcrumb of what actually ran.
- **Center over the brain** — (optional, lowest priority) 1px pheromone arcs that pulse cyan only on the
  exact bus event that touched that channel; mounted FLAT in the portal, never scene-pinned.
- **Right console** — real pheromone counts, beacon lines mapping live metric values, agent cards that light
  only when a real tool owns them.
- **Terminal log** — the causality ledger: timestamped facts, a verdict column (PASS/FAIL) and an
  earned-autonomy delta column, both from real signals.
- **Command bar** — the pilot vessel: turn-state on Execute (driven by HONEST state, not a fake %), a brain
  chip, a live engaged counter, a directive echo, a one-shot submit sweep.

Governing read: **"rest is not death."** Idle shows honest zeros, dashes, and baseline hairlines. The instant
a real directive lands, the instrument animates together from real events.

---

## 2. THE LIVE-PHASE DERIVATION (the soul's spine — must be HONEST)

The single most important honesty fix: the mode/phase the HUD shows must reflect the **real live turn phase
derived from the cognition bus**, not an operator-toggled static `modeCopy` map. There is no phase event in
the bus, so we DERIVE it deterministically from the events that already exist. No new event is invented.

```
livePhase (derived, with timestamps; reset to REST on directive end or after idle window):
  • directive received                          -> ORCHESTRATE briefly (the mesh snaps to attention)
  • burst (a labeled recall touching a trail)   -> OBSERVE     (mapping/recalling knowledge)
  • agent-dispatch w/ "tool engaged: <name>"    -> ORCHESTRATE (dispatching real tools)
  • generating === true (model producing text)  -> SYNTHESIZE  (reasoning/creating)
  • synthesis (cycle complete) / no activity    -> REST        (honest standby)
```

Precedence while a turn is live: a fresh `tool engaged` (last ~4s) reads ORCHESTRATE; else `generating`
reads SYNTHESIZE; else a recent `burst` reads OBSERVE; else REST. This is a small reducer over the bus
(`useReducer` or a `phaseRef` + `setPhase`), all from events the subscriber at `SuperbrainHUD.tsx:682-808`
already receives. **REST is a first-class phase, not an absence** — it renders honest standby copy, not
invented work.

The `mode`/`onModeChange` prop and the `MODE_RAIL` buttons remain as the **operator's manual override** (he
can pin a lens), but the DEFAULT and the live truth is the derived phase. When the operator has not pinned,
the rail's active item follows `livePhase`. When he pins, his choice wins and a tiny `pinned` marker shows
(honest: "you are steering the lens"). The headline + subtitle (`modeCopy`, lines 38-51) are rewritten to
describe the phase truthfully and to include a REST entry:

```ts
const PHASE_COPY: Record<Phase, { title: string; detail: string }> = {
  rest:        { title: 'Holding at the knowledge horizon', detail: 'Standby. No directive in flight.' },
  observe:     { title: 'Observing the knowledge horizon',  detail: 'Recalling trails and mapping relationships.' },
  synthesize:  { title: 'Synthesizing the directive',       detail: 'Model reasoning toward one execution.' },
  orchestrate: { title: 'Orchestrating the agent mesh',     detail: 'Dispatching and monitoring real tools.' },
};
```

Note: ZERO em-dashes; honest REST copy; subtitles describe REAL phase, not fiction.

---

## 3. The HONEST PURGE (delete list — do it, do not merely claim it)

Every item below is **removed or replaced with a real readout**. This is the load-bearing anti-slop work; do
it FIRST so the renovation cannot hide slop behind new chrome.

| # | Slop to remove | Location | Action |
|---|---|---|---|
| P1 | **Fake footer build stamp** `GAGOS v2.6 — autonomous core` | `SuperbrainHUD.tsx:1079-1081` (`.hud-footer`) | **DELETE the element.** It asserts a version that means nothing. No replacement (the footer was pure decoration). If a footer slot is wanted, it may show a REAL readout only (e.g. `chainEntries` ledger size when `telemetry.chainValid===true`), else render nothing. |
| P2 | **`SUPERMIND / NN` build-tag lore** | core-readout `<h2>` `:1019-1021`; brand `build-tag` `AUTONOMOUS CORE` `:880` | The `/ NN` is `currentMode.num` dressed as a build number — **remove the `/ NN`**. Keep the `SUPERMIND` wordmark as the product name (it is the literal name, not a fake metric). Replace the `core-sub` line (`:1022-1024`) "COGNITIVE SYNTHESIS CORE — ..." with the **real derived phase** label (`OBSERVE / SYNTHESIZE / ORCHESTRATE / STANDBY`) + the honest link state. The brand `build-tag` `AUTONOMOUS CORE` is a tagline, not a fake number; keep it (it claims nothing falsifiable). |
| P3 | **EVERY em-dash** (~10 user-visible) | footer `:1080`; core-sub `:1023`; tooltips `:1005,:1006,:939,:956,:971,:984`; objective-tree placeholders `:1133-1134` | **ZERO em-dash in the final file.** Replace `—` with ` · ` (middle dot, already a codebase convention) in prose/tooltips, and with `--` (two hyphens) in the objective-tree empty-slot placeholders. The footer em-dash vanishes with the footer (P1). Build gate: `grep -n "—"` over the diff must return NOTHING. |
| P4 | **The AUTONOMY lightning emoji** ⚡ | `:906` `` `⚡${telemetry.earnedAutonomy.earned}` `` | A decorative glyph on a real-numbers HUD is the slop tell. **Drop the emoji, keep the real number:** render `AUTONOMY <strong>{telemetry.earnedAutonomy.earned}</strong>`. The label "AUTONOMY" already carries the meaning. |
| P5 | **Idle theatre: cycling agent timer** | `useCyclingAgent` `:246-264`; `AGENT_DETAILS` canned strings `:121-140`; `AGENT_STATES` cycle | **DELETE the timer churn and the canned-string cycle.** Agent cards show real state ONLY: `processing` + `running <tool>` when a real `toolPulse` owns the card; the directive-surge `FORCED_ON_DIRECTIVE` choreography may stay for the first ~5s of a real turn (it is keyed to a real `directive` event); otherwise the card reads honest **`standby`** with NO invented detail line. `AGENT_DETAILS` is deleted. |
| P6 | **`useDecodeOnHover` scramble** | `:301-352` + usage in `AgentCard` `:540,:548` | **DELETE.** The hacker-scramble reveal is an AI-slop tell and fakes computation on hover. Agent names render plainly. (Removes `DECODE_GLYPHS`, `decodeActive`, the hook, and its call.) |
| P7 | **`SOURCE_MESH_LABELS` offline carousel** | `SOURCE_MESH_LABELS` `:158-166`; `useCyclingLabel` `:440-450`; `sourceMeshLabel`/`intakeLabel` `:587,:839,:1155` | **DELETE the carousel.** Fabricating motion during an outage is exactly the dishonesty the soul forbids. Offline, the intake heading shows an honest static `LINK OFFLINE · intake paused` (no rotation). Online it shows the real `Pheromone map · N trail(s) · M verified` (already at `:1153-1155`). Removes `useCyclingLabel` if no other caller remains. |
| P8 | **Fabricated `objectivePct` heuristic** | `:642-646` (`generating ? 35 + engagedLive*12` / `60 + activity*19`) | **DELETE the invented formula.** Presenting `35 + engagedLive*12` (or `60 + activity*19`) as "completion %" is a made-up progress number. Replace the objective card's `%` with **honest counts + state** (see §4 ROW set). The `objectivePct`-driven progress bar fill is removed; **do NOT drive any "forward motion" ring from a fake %** (see §7 command bar). Where `telemetry.trails>0`, the *real* verified ratio (`100*verified/trails`) MAY be shown but **labeled honestly as `verified share`, not "objective %"** — it is a real metric, not a task-completion estimate. |
| P9 | **Canned sparkline hills** | `SPARKLINES` `:87-92`, `buildSparkPaths` `:94-106`, `SPARK_PATHS` `:108`, and the fallback branch in `SourceRow` `:476-484` | **DELETE the canned hills and the fallback.** The beacon-line (§5) replaces the sparkline. `useMetricHistory` stays available but the row no longer invents hills before two real samples exist; with <2 samples the beacon sits at its honest baseline opacity. Remove `SPARKLINES`/`SPARK_PATHS`/`buildSparkPaths` once the row stops referencing them (eslint no-unused gate). |
| P10 | **`IDLE_LORE` + `IDLE_DELAYS`** review | `IDLE_LORE` `:188-196`, `IDLE_DELAYS` `:199`, the offline ticker `:810-825` | **Demote, do not fabricate.** The ticker already fires ONLY while the link is down (`getLinkState()` false), so it is offline-only — but the lines themselves (`Drift correction 0.0021`, `Tether integrity 99.97%`) are invented precision. **Replace `IDLE_LORE` with honest offline status lines** (e.g. `Link offline · awaiting adapter`, `Reconnect attempt pending`) OR delete the offline ticker entirely and let the terminal sit still while offline (preferred: a silent terminal is more honest than invented chatter). Recommended: **delete the offline ticker** (`:810-825`) and `IDLE_LORE`/`IDLE_DELAYS`. |

### 3.1 Status dots + glyphs — explicit RULE (state, not decoration)

For every dot/glyph kept, add a code comment: `/* state, not decoration: encodes <real value> */`. The ruling:

- **`status-dot--live` / `status-dot--down`** (`:887`) — KEEP. Encodes real `linkUp` (adapter poll reached the
  AI-OS). Color: `--state-ok` live / `--state-busy` down. Comment it `state, not decoration`.
- **`brain-dot--local` / `brain-dot--cloud`** (`:923-925`) — KEEP. Encodes real `activeBrain.privacy`
  (`--state-ok` local / `--state-busy` cloud). Comment it `state, not decoration`.
- **`mode-dot`** (`:1116`) — KEEP only as the active-phase indicator; it must reflect the **derived
  livePhase / pinned override**, not a static per-button decoration. If it cannot encode that, REMOVE it.
- **AUTONOMY ⚡ emoji** — REMOVE the emoji (P4); the number stays.
- **`execute-return` ⏎ glyph** (`:1071-1073`) — KEEP. It is a real affordance (Enter submits), not
  decoration; it is a keyboard hint. Comment it as an affordance hint.

No other decorative dots/glyphs may be added.

---

## 4. LEFT "ACTIVE COGNITION" panel — full buildable detail (LEAD; the operator's specific complaint)

The operator's complaint: this panel **feels static**. Today it shows a fixed `modeCopy` title from the
operator-set `mode` prop, three mode buttons, and an `objective-card` whose `%` is the fabricated heuristic
(P8). At idle it reads like a poster. The fix makes it the live cadence of REAL work, honest at rest.

DOM lives in the scene-pinned `<Html position={[-4.8,-1.7,0]}>` console (`:1093-1142`) — **we do not move
it** (moving it would touch scene-pin coordinates; out of scope and risky). We only change its interior JSX
and styles. The console is NOT interactive overlay-over-brain; it is a pinned panel that already exists, so
editing its contents does not breach the 3D interaction contract. (The CENTER pheromone overlay is the only
thing that must avoid `<Html position>` — see §8.)

### 4.1 What REAL backend signal drives each part

| Element | Real signal | Source |
|---|---|---|
| Eyebrow `ACTIVE COGNITION` | static label (role eyebrow) | unchanged |
| Phase headline + subtitle | **derived `livePhase`** (REST/OBSERVE/SYNTHESIZE/ORCHESTRATE) + `pinned` override | §2 reducer over the bus |
| Mode rail active item | `livePhase` (or operator pin) | §2 |
| ROW A `PHASE` | `livePhase` word | §2 |
| ROW B `TOOLS THIS TURN  N / M` | `engagedLive` / `knownTools` | `:596-597,733-734` (real distinct-tool Sets) |
| ROW C heartbeat hairline + pulse | `toolPulse` null -> non-null transition | `:601,736` (set only on real `tool engaged:`) |
| ROW D `last tool · elapsed` | `recentSteps[last]` + a 1s elapsed counter that runs **only while `generating`** | `:599,735` + `generating` `:586` |
| Breadcrumb (last 2 real tools) | `recentSteps[]` | `:599,735` |
| `verified share` (optional, replaces the fake %) | `telemetry.trails>0 ? round(100*verified/trails) : null` | `:644-645`, labeled honestly |

Nothing here is invented. Idle: PHASE = `STANDBY`, TOOLS = `0 / 0`, heartbeat = flat hairline, last tool =
`--`, breadcrumb = `--` / `--`, verified-share hidden (null at idle/offline).

### 4.2 The JSX (replacing `:1095-1136` interior; structure, not verbatim)

```
<aside className="left-console glass-surface" aria-label="Active cognition">
  <div className="eyebrow"><span /> ACTIVE COGNITION</div>

  {/* HONEST live phase — derived from the bus, not an operator toggle */}
  <h1>{PHASE_COPY[livePhase].title}</h1>
  <p className="cognition-detail">{PHASE_COPY[livePhase].detail}</p>

  {/* Mode rail = operator's manual lens override; defaults to follow livePhase */}
  <div className="mode-rail" role="group" aria-label="Cognitive lens">
    {MODE_RAIL.map(item => (
      <button ... aria-pressed={activeRailId === item.id}
              className={`mode-button ${activeRailId === item.id ? 'is-active' : ''}`}>
        <span className="mode-num">{item.num}</span>
        <span className="mode-copy"><strong>{item.label}</strong><small>{item.sub}</small></span>
        {/* state, not decoration: lit only on the active (live or pinned) lens */}
        <i className="mode-dot" />
      </button>
    ))}
    {pinned ? <span className="lens-pinned">pinned</span> : null}
  </div>

  {/* DISPATCH CADENCE — the live heartbeat of real work (replaces the fake objective %) */}
  <div className="dispatch-cadence" aria-live="polite" aria-atomic="true">
    <div className="cad-row"><span>PHASE</span><strong>{PHASE_LABEL[livePhase]}</strong></div>
    <div className="cad-row"><span>TOOLS THIS TURN</span>
      <strong className="tabnum">{engagedLive} / {knownTools}</strong></div>

    {/* heartbeat hairline; the pulse is a NON-BLURRED sibling fired by React key on real dispatch */}
    <div className="cad-beat">
      <i className="cad-beat-line" aria-hidden />
      <i key={toolPulse ? `${toolPulse.row}-${dispatchSeq}` : 'idle'}
         className={`dispatch-pulse${toolPulse ? ' dispatch-pulse--fire' : ''}`} aria-hidden />
    </div>

    <div className="cad-row cad-row--sub">
      <span className="cad-last">{recentSteps[recentSteps.length-1] ?? '--'}</span>
      <span className="cad-elapsed tabnum">{generating ? elapsedLabel : ''}</span>
    </div>

    {/* honest, optional, only when real trails exist — labeled as a metric, NOT "objective %" */}
    {verifiedShare !== null ? (
      <div className="cad-row cad-row--share"><span>VERIFIED SHARE</span>
        <strong className="tabnum">{verifiedShare}%</strong></div>
    ) : null}

    <div className="objective-tree">
      <p className="is-lead">{lastDirective || '--'}</p>
      <p>{recentSteps[recentSteps.length-2] ?? '--'}</p>
      <p>{recentSteps[recentSteps.length-1] ?? '--'}</p>
    </div>
  </div>
  <i className="glass-grain" aria-hidden />
  <i className="console-glow" aria-hidden />
</aside>
```

`elapsedLabel`: a `setInterval(…,1000)` started in a `useEffect` keyed on `generating`, **gated on
`prefersReducedMotion()`** (no interval under reduced motion; show the last static value), cleared when
`generating` flips false. Formats `Ns` / `Nm Ns`. `dispatchSeq` is a ref incremented on every real
`toolPulse` set so the React `key` changes and re-fires the one-shot pulse.

### 4.3 What slop is REMOVED here

- The static operator-only `modeCopy` headline -> replaced by **derived live phase** (§2). This is the direct
  fix for "feels static."
- The fabricated `objectivePct` (P8) and its progress bar -> replaced by honest **counts + phase + real
  dispatch heartbeat**. No invented completion number, no fake forward-motion fill.
- The em-dash placeholders (`:1133-1134`) -> `--`.

### 4.4 Motion (all compositor-only, reduced-motion gated)

- **Heartbeat pulse** `dispatch-pulse--fire`: a NON-BLURRED sibling `<i>`, `@keyframes` on `transform: scaleX`
  + `opacity` only, 450ms `--ease-out-quart`, one-shot via React `key`. Fires ONLY on a real `tool engaged:`
  dispatch. The blurred glass parent is never animated (paint-trap law).
- **Phase headline swap**: opacity cross-fade 150ms `--ease-out-quart` on phase change (a real transition).
- **Breadcrumb enter**: 150ms `translateY(4px)->0` via React `key` on `recentSteps` change.
- **Counter / elapsed**: instant integer / 1s step, NO tween (event-driven integers; `useTweenedMetric` is
  deliberately NOT used here — gliding a discrete tool count would be theatre).
- Idle: zero motion. The hairline sits flat. (Honest rest.)

### 4.5 CSS to add (lab `globals.css`)

`.dispatch-cadence` (1px hairline rows, `var(--mono)` + `font-variant-numeric: tabular-nums`),
`.cad-row`, `.cad-beat`, `.cad-beat-line`, `.dispatch-pulse` + `@keyframes dispatch-pulse-fire`
(transform/opacity only), `.cad-elapsed`, `.cad-row--share`, `.lens-pinned`, and a reduced-motion fallback
block forcing the pulse to its static end-state. NO new card box; rows insert into the existing console
interior. No animated `box-shadow`/`border`/`background`/`backdrop-filter` anywhere.

### 4.6 8-check harmonization (this panel)

1. One accent: cyan only on the heartbeat pulse + active mode-dot; counts/labels neutral. `--state-ok`
   green is not used here. **Y.** 2. Canon glass: reuses the existing `.left-console.glass-surface` recipe
   untouched. **Y.** 3. Shared cadence: 150ms quart fades, 450ms quart pulse. **Y.** 4. Calm but alive:
   motion only on real dispatch/phase change; idle flat; RM gated. **Y.** 5. No paint-on-blur: pulse is a
   non-blurred sibling, transform/opacity only. **Y.** 6. Both soul verbs, real data: WORKING (live phase +
   real tool counts + heartbeat) and the VOYAGE (settling entrances, honest standby). **Y.** 7. Depth: the
   console keeps its rim + cast shadow + scene-bleed. **Y.** 8. Type: mono + tabular-nums on every changing
   figure; one eyebrow all-caps role; `Outfit` only on the hero title. **Y.**

---

## 5. Right console · KNOWLEDGE INTAKE

**Real signals:** `telemetry.{trails,verified,latencyMs,avgToolCalls}`, `useMetric(key)`,
`useMetricHistory(key)`, `sourcePulse`, `toolPulse`, `engagedLive`, `knownTools`, `linkUp`.

**Changes:**
- Heading: online -> real `Pheromone map · N trail(s) · M verified` (already `:1153-1154`). Offline -> honest
  static `LINK OFFLINE · intake paused` (the `SOURCE_MESH_LABELS` carousel is DELETED, P7).
- `SourceRow`: **remove the sparkline SVG + `SPARK_PATHS`/`SPARKLINES`/canned fallback** (P9). Replace with a
  **1px beacon line** whose opacity = `clamp(0.2, useTweenedMetric(value)/100, 0.95)`. With <2 real samples
  it sits at honest baseline (0.2), never invented hills.
- Intake `+` glyph per row on real `sourcePulse` (transient, 150ms enter, 2s fade) — keep `source-orb--flash`
  (transform scale, safe).
- Agent cards: **`useCyclingAgent` + `AGENT_DETAILS` + `useDecodeOnHover` DELETED** (P5, P6). A card is
  `processing` + `running <tool>` only when a real `toolPulse.row===index`; the `directive`-keyed
  `FORCED_ON_DIRECTIVE` surge may fill the first ~5s; otherwise honest `standby` with no detail line. Add a
  2px left-edge accent bar (plain non-blurred child div) on the active card.
- Agent-mesh heading numbers stay real (`engagedLive / knownTools engaged · avg N/turn`, `:1181-1184`), null-
  guarded as today.

**Slop removed:** P5, P6, P7, P9 (carousel, scramble, cycling timer, canned hills).
**Motion:** intake glyph 150ms translateX+opacity; beacon opacity from `useTweenedMetric` (350ms / instant
under RM); edge-bar opacity 80ms on a plain child. No paint-on-blur.
**Harmonization:** one accent (beacon + glyph + edge), neutral data; canon glass untouched; real-data only;
tabular-nums. 8/8.

---

## 6. Terminal log

**Real signals:** `termLine.{time,text}`; verdict from `knowledge-acquired` label `VERIFICATION GREEN/RED`
(the adapter emits these); delta from `telemetry.verified` gain via a `prevVerifiedRef`; header brain tag
from `activeBrain.{model,privacy}`.

**Changes:** convert `.terminal-log p` to a 4-col grid `[ts][label][verdict][delta]` (`38px 1fr 90px 52px`).
New `<b className="term-verdict--pass|--fail">PASS|FAIL` and `<i className="term-delta--earned">+N` (only when
N>0). `TERM_BUFFER_MAX` stays 4.

**CONCRETE DEFECT FIX (undefined vars):** the prior spec used `var(--pass)` and `var(--earned)` — those are
NOT defined in `globals.css`. Define the verdict/delta colors against EXISTING canon tokens:
```css
.term-verdict--pass  { color: var(--accent); }       /* cyan = the one accent, sanctioned for PASS */
.term-verdict--fail  { color: var(--state-busy); }   /* amber = canon fail/busy state */
.term-delta--earned  { color: var(--accent); }        /* a real hash-chain growth = an accent moment */
```
No new variable is introduced; no undefined var is referenced. (If a distinct earned hue is later wanted,
add a real `:root` token first; never reference an undefined one.)

**Slop removed:** the offline `IDLE_LORE` ticker (P10) — terminal sits silent while offline rather than
inventing precision lines.
**Motion:** new-line `term-mount` 120ms `translateY(6px)` (transform/opacity, rides the existing `term-fresh`
class); verdict/delta colors are STATIC paint classes (no animation). RM fallback collapses the mount.
**Harmonization:** accent for PASS/earned (real events), amber for FAIL (canon state); mono + tabular ts;
no paint-on-blur. 8/8.

---

## 7. Command bar · DIRECT THE SUPERMIND

**Real signals:** `generating`, `activeBrain`, `engagedLive`, `knownTools`, `lastDirective`, `approvalHold`;
events `route`/`directive`/`agent-dispatch`/`synthesis`.

**Changes (all suppressed under `approvalHold`):**
1. **Turn-state on Execute** — button text reflects HONEST state: `Execute` -> `Streaming...` (while
   `generating`) -> `Done` (on `synthesis`) -> `Execute`. **The ring/arc on Execute is driven by HONEST
   STATE, NOT a fake % .** Option A (preferred): an indeterminate "working" arc that simply spins/pulses
   while `generating` (it asserts "working," not a false completion fraction). Option B: omit the ring and
   rely on the text + a subtle border-rim brightness toggle (`--rim-top` var, no paint animation). **Do NOT
   set dasharray from `objectivePct`** — that number is deleted (P8).
2. **Brain chip** — privacy dot + provider/model on `route` (real).
3. **Engaged counter** `[N tools · S session]`, N in accent; +1 pulse `scale(1.12)` 120ms on real `toolPulse`.
4. **Directive echo** — first 40 chars + word count of `lastDirective`; clears on input focus.
5. **Submit sweep** — one-shot 1px cyan line in `.command-field` (non-blurred child), `scaleX(0->1)` 300ms +
   fade, never loops.

**Slop removed:** the fake-%-driven progress ring (P8 dependency). Honest "working" indeterminate state
replaces a fabricated completion fraction.
**Motion:** chip 200/300ms opacity; counter 150ms appear / 120ms +1 pulse / 220ms vanish; echo 150/100ms;
sweep 300ms one-shot; all gated by `prefersReducedMotion()`. No paint-on-blur (sweep + ring are non-blurred
children; rim uses the `--rim-top` var toggle, not animated paint).
**Harmonization:** one accent (ring/counter/sweep); amber only via the existing `is-approval-hold` state;
canon command-bar glass untouched. 8/8.

---

## 8. Topbar + sovereignty row

**Real signals:** `linkUp`, `telemetry.latencyMs`, `activeBrain`, `telemetry.earnedAutonomy.earned`,
`approvalHold`, `telemetry.chainValid`; dispatch glyphs from `agent-dispatch`/`tool engaged:`.

**Changes:** keep brand, system-summary, FIDELITY/SKY/SURFACE/SOUND, shield as-is (all already real). Apply
the purge: **drop the AUTONOMY ⚡ emoji, keep the number** (P4); fix tooltip em-dashes to ` · ` (P3, lines
939/956/971/984/1005/1006). Additive REAL readouts: (a) latency `.val-tick` micro-breathe on change (opacity
0.5->1, 200ms); (b) a small **dispatch ribbon** (last 3 real tool glyphs, invisible before the first real
turn); (c) optional knowledge-waveform SVG (blended 4-channel real metric area path) as a non-blurred child
overlay — its endpoint dot is the ONE allowed perpetual ambient loop (the brain never stops voyaging). Shield
state via class swap on the SVG only.

**Slop removed:** the ⚡ emoji (P4); em-dashes (P3).
**Motion:** glyph mount 200ms translateX+opacity; latency val-tick 200ms opacity; wave path rAF tween 350ms;
wave dot `--ease-loop` 2.2s (the single perpetual loop). All non-blurred children / SVG-attr writes; RM gated.
**Harmonization:** one accent (wave dot/rim, ribbon); `--state-ok`/`--state-busy` only on the link + brain
state dots; canon `.topbar` glass untouched. 8/8.

---

## 9. Center pheromone overlay (OPTIONAL · lowest priority · strict placement)

If built at all, it is 4 concentric 1px stroke-only SVG arcs (RESEARCH/MEMORY/TOOLS/SIGNALS), each pulsing
cyan ONLY on the exact bus event that touched its channel (`knowledge-acquired` via `SOURCE_MATCH_ORDER`,
`agent-dispatch` via `agentRowForTool`), with a 3-o'clock real `useMetric` label.

**CONCRETE DEFECT FIX (frozen 3D contract):** it **MUST mount in the `#hud-portal-root` portal subtree**
(the flat 2D DOM created at `WorkspaceCanvas.tsx:254`, mounted via `createPortal` at `SuperbrainHUD.tsx:1083`)
— a positioned `pointer-events:none` SVG child of `.hud-shell`. It must **NEVER** be a scene-pinned
`<Html position>` console (unlike the left/right consoles at `:1093,:1144`). A scene-pinned overlay would
breach the frozen 3D-scene interaction contract: it re-projects per frame and would steal brain orbit/drag.
`pointer-events:none` + no `backdrop-filter` ancestor + `isolation:isolate`; glow via SVG `feGaussianBlur` on
its own element, never `box-shadow` on glass.

Idle: a faint `<animate>` stroke-opacity breathe (0.18;0.28;0.18, 2400ms) — honest ambient, gated by the
global RM block. **If time-boxed, skip this panel entirely; the soul does not depend on it.**

---

## 10. Shared tokens, motion, one-accent audit

- **No new accent.** Cyan `--accent #5ce1e6` is the only accent (topbar wave/ribbon, left heartbeat, center
  pulse, right beacon/glyph/edge, terminal PASS/earned, command ring/counter/sweep).
- **One-accent audit must ACCOUNT for canon state hues** so they are not mis-flagged: `--state-ok #58d68d`
  (link-live dot, brain-local dot — `globals.css:17`) and `--state-busy #e0a84f` (link-down, brain-cloud,
  terminal FAIL, approval hold — `globals.css:18`) and tamper-red `#ff5c5c` (`:576`) are **sanctioned state
  semantics, not accents.** The audit passes a panel that uses ONLY {neutral text + the one accent + these
  three state hues, each on a real state}.
- **Aliases / undefined vars:** there is NO `--pass`/`--earned`/`--accent-soft`/`--accent-mid` requirement.
  Terminal verdict/delta use `var(--accent)` and `var(--state-busy)` (§6). If a beacon-base or dot-glow soft
  tint is genuinely needed, add a REAL `:root` token (`--accent-soft: rgba(92,225,230,.18)`) in the same
  commit — **never reference a var that is not defined.** Grep gate: every `var(--X)` the diff introduces must
  resolve to a `--X:` in `:root`.
- **New duration tokens** (add to `:root` only if used): `--dur-tick:200ms; --dur-pulse:450ms`. Reuse the
  existing four easing tokens (`globals.css:24-29`).
- **Paint-trap law (build gate):** never transition/animate `box-shadow`/`border`/`background`/
  `backdrop-filter` on any backdrop-filtered element or its re-raster ancestor. All motion is compositor-only
  (`opacity`/`transform`) on non-blurred children/siblings, or SVG-attr writes on a non-blurred SVG layer.
- **Reduced motion:** the global block (`globals.css:1603+`) collapses `*`; additionally every new JS timer/
  rAF checks `prefersReducedMotion()` (`SuperbrainHUD.tsx:267`) before starting, and every new keyframe gets
  an explicit instant end-state fallback.
- **Cockpit density:** 1px hairlines, no new card box, mono + tabular-nums on all changing figures, **zero
  em-dashes**, no version stamps, no decorative dots/glyphs beyond the state-encoding ones ruled in §3.1.

---

## 11. Build order, gates, and freeze

### Phase A — Purge first (the honesty pass)
Do §3 P1-P10 + §2 phase reducer + the em-dash/emoji/undefined-var fixes BEFORE any new chrome. Run
`npm run lint && npm run build` and confirm the file is smaller and slop-free. Grep gates:
`grep -n "—"` (em-dash) = empty; `grep -n "⚡"` = empty; `grep -n "GAGOS v2.6"` = empty;
`grep -n "var(--pass)\|var(--earned)"` = empty.

### Phase B — Build panels in dependency order (lab `SuperbrainHUD.tsx`)
1. **Left ACTIVE COGNITION** (§4) — the operator's complaint; the phase reducer + dispatch cadence.
2. **Terminal log** (§6) — verdict/delta grid (uses real tokens now).
3. **Right console** (§5) — beacon replaces sparkline; agent cards honest.
4. **Command bar** (§7) — honest turn-state, no fake ring.
5. **Topbar** (§8) — ribbon + waveform; purge applied.
6. **Center rings** (§9) — optional, last, FLAT in the portal.
After each: `npm run dev` -> run a real directive, watch live bus reaction; idle 30s to confirm
rest-not-dead (zeros/dashes/flat, NO fake motion).

### Phase C — Lab gates
```
cd "GAG demo/gag-orchestrator"
npm run lint        # eslint — TSX clean, no dead exports from the purge
npm run build       # next build
npm run test        # vitest run — existing suite green
```
Add focused lab tests: livePhase derivation (burst->observe, generating->synthesize, tool engaged->
orchestrate, synthesis/idle->rest, precedence), `prevVerifiedRef` delta (non-negative, undefined at
0/offline), verdict-label mapping, `engagedLive` reset on `directive`. No WebGL needed.

### Phase D — Golden eyeball
`node tools/capture-canon.mjs hud-before` (if not already in `goldens/`), apply, rebuild,
`node tools/capture-canon.mjs hud-after`. Produce the before/after idle pair; the `-brain.png` crop MUST be
pixel-identical (the HUD never touches the brain). Capture a live-turn frame to prove motion reads as real
work. FIDELITY IS SACRED.

### Phase E — Canon-freeze guard + port
1. **Freeze check (mechanical + untracked):** the diff must list ONLY
   `src/components/ui/SuperbrainHUD.tsx`, `src/app/globals.css`, `src/test/*`. **Run both:**
   `git -C "GAG demo/gag-orchestrator" diff --name-only` AND
   `git -C "GAG demo/gag-orchestrator" status --porcelain` (the porcelain catches **UNTRACKED** files under
   `components/canvas/` that a plain diff misses). Any `components/canvas/`, `public/models/`,
   `public/textures/` path (tracked OR untracked) = STOP, freeze breached.
2. **Port:** `npm run port`. The manifest-drift tripwire (`port-to-frontend.mjs:82-105`) aborts on import
   drift; no new module is added, so it passes; product `superbrain.css` + HUD regenerate.
3. **Product gates:** `cd frontend && npm run lint && npm run build && npm run test && npm run dev`
   (`http://localhost:5173/?ui=superbrain` default; confirm `?ui=classic` still renders).

### Phase F — Operator sign-off
Present before/after idle + live-turn frames in HIS browser (parity proven in his browser, not the probe).
Land only on approval. Refresh Tier-1 docs + RESUME + CEO_LOG per the doc-currency convention; never rewrite
dated evidence.

---

## 12. Risks

1. **Phase reducer correctness (new, highest).** The derived livePhase is the soul's spine; a wrong
   precedence makes the HUD lie. Mitigation: the §2 precedence is unit-tested headless; REST is explicit;
   timestamps decay (tool engaged ~4s window) so a stale event never pins a false phase.
2. **CSS edit-target confusion.** All CSS in lab `globals.css`; product `superbrain.css` is generated.
3. **Center overlay placement.** Portal-flat only (§9); never `<Html position>`; `pointer-events:none`;
   verify brain orbit/drag after build. Skip if time-boxed.
4. **Dead exports after the purge.** Removing `useCyclingAgent`/`AGENT_DETAILS`/`useDecodeOnHover`/
   `SOURCE_MESH_LABELS`/`SPARKLINES` must remove ALL their references together or eslint no-unused fails.
   Mitigation: lint after Phase A.
5. **Undefined-var regression.** Every new `var(--X)` must resolve in `:root`. Grep gate in §10.
6. **Em-dash leakage.** `grep -n "—"` over the diff must be empty (the prior file had ~10).
7. **Telemetry null at idle.** Every new telemetry readout null-guarded + suppressed offline (never a
   fabricated number), as the current code already does at `:1183`.
8. **Reduced-motion drift.** Every new JS timer/rAF gated on `prefersReducedMotion()` in addition to the
   global media block.
9. **Port GLB strip (adjacent, not a regression).** `npm run port` strips the product `brain.glb`; the
   freeze check runs on the LAB tree pre-port where the GLB is never modified.

---

**Files this plan authorizes editing (lab):**
`C:\Users\kumar\ai-editor\GAG demo\gag-orchestrator\src\components\ui\SuperbrainHUD.tsx`,
`C:\Users\kumar\ai-editor\GAG demo\gag-orchestrator\src\app\globals.css`,
and new tests under `C:\Users\kumar\ai-editor\GAG demo\gag-orchestrator\src\test\`.
**Product mirror (port output only, never hand-edited):**
`C:\Users\kumar\ai-editor\frontend\src\superbrain\components\ui\SuperbrainHUD.tsx`,
`C:\Users\kumar\ai-editor\frontend\src\superbrain\superbrain.css`.
**Frozen, never touched:** everything under `components\canvas\` (incl. `WorkspaceCanvas.tsx` that owns
`#hud-portal-root`), `public\models\brain.glb`, `public\textures\brain\`.
