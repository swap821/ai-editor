# 🎬 MOTION-WOW PLAN — 60-70% → wow (phase/posture transition choreography)

Operator mandate (2026-06-23): GOAT transformation; smooth, clean, beautiful "wow" transitions
between phases/postures. Static look ≈85%; **motion ≈50%** — the drag. Root cause: every
work-phase transition routes through a **flat `PHASE_TARGETS` table** (`pointFieldLifecycle.ts`) +
**simultaneous per-uniform `THREE.MathUtils.damp()`** in the frame loops = the "uniform reflex"
(smooth but characterless, every change identical). The arrival cinematic is the ONE staged
transition (`openingMotion.ts` cubic-bezier + asymmetric ignition bell) — the **pattern to copy**.

Source: 7-agent ultracode motion audit (`gagos-motion-audit`, run wf_58973551-9b5) weighted
Jakub (production polish) + Jhey (wow) — rare-trigger "watch it transform" experience, expressive
motion welcome (NOT Emil's "unnoticed" rule). Verify every moment LIVE in his Edge (motion can't
be judged from stills). Laws hold: data-true, approval gate, frozen core, sacred palette,
tests-green, his-eye-is-arbiter.

## The wow recipe
Every signature moment gets STAGES: **anticipation → action → overshoot/settle → secondary motion**,
SEQUENCED (elements transition in order, not simultaneously), with authored ease-out curves
(expo/quint/easeOutBack) — `damp()` kept ONLY for genuinely ambient channels (breath, flow speed,
cursor lean). Every moment ships a `prefers-reduced-motion` branch (positional → instant; luminance → short crossfade).

## Structural enabler (do alongside the first BODY-transition moment)
- Add `phaseEnteredAt` to `organismPhaseBus.setOrganismPhase` so consumers compute `sincePhase`.
- Add an optional per-phase TRANSITION descriptor next to `BODY_POSTURES` (`{leadOrgan, stageMs:[spine,cortex,nerve], ease}`) so choreography is DATA the scene reads, not scattered constants. (`bodyPosture.ts`, `organismPhaseBus.ts`)
- Reusable easing toolkit: `easeOutBack` + overshoot-then-settle helper; reuse `cubicBezier()`/`ignitionPulse()` from `openingMotion.ts` as the shared curve vocabulary.

## Signature moments (build order)

### 1. ★ PANEL MATERIALIZE-BLOOM — RECOMMENDED FIRST  [high impact / medium effort]
Self-contained in `MaterializedTab.tsx` (per-tab clock `tab.phaseStartedAt` @1326-1340; no bus). Builds the shared easing toolkit. Fires on every directive = most-watched.
- Add `easeOutBack(t, overshoot≈1.7)` helper + residual damp-to-settle; replace the symmetric `smoothstep` on slab scale (@145-147, used @1531-1538) so Y overshoots to ~1.06 then settles to 1.0.
- Open Y first + slightly ahead of x/z (start Y ~0.06 not 0.01) → unfurls like a membrane, not a pop-from-zero.
- Ease `reachProgress` through expo/quint into `getPointAt` AND the tube draw-range (@1327-1358) so the nerve LUNGES from the vertebra and decelerates into the anchor; ~60-90ms socket-pool anticipation before launch.
- Per-layer stagger on the shared `slabProgress` (@1540-1603): shell 0.0 / rim 0.15 / header+title 0.3 / code+dashboard 0.45 / halo 0.6, each its own ease-out sub-progress.
- On reaching→unfurling handoff: one-shot socket flash (1.15→1.4→1.15 + opacity, ~160ms ease-out @1609-1620/1834-1845) + bead-burst into slab origin (nerve visibly CAUSES the bloom); overlap unfurl ~10% before reach hits 1.0.
- Reduced-motion (@1311-1319): replace instant pop with ~150ms opacity-only crossfade at full scale.

### 2. SUMMON / WAKE — "it noticed me" + the being comes alive  [high / medium]  ✅ DONE (wake-catch earlier + 03e5121)
Landed: (a) wake-catch (uAwaken easeOutBack on notice); (b) ARRIVAL CASCADE — arrivalLight smoothstep start offset by vAxis so the being lights roots→cortex (wave up), REST byte-identical; (c) WAKE WAVE — uWakeWave luminance pulse rushes up the body (easeOutExpo 0.5s) on the notice rising edge, hands into the cortex heat. Reduced-motion: cortex heat only, no travelling pulse. Dev scrub: `window.__ARRIVAL_PREVIEW` / `__WAKE_PREVIEW`. NOT done (deferred, risky): camera dolly-in (OrbitControls owns distance); nerveStaggerMs.
Needs the structural enabler (sincePhase). 3-beat wave UP the body off one clock:
- Drive the cloud `uAwaken` from the SAME `awakenNotice()` envelope the cortex mesh uses (publish on a bus / read sinceState) instead of damp rate 4; add overshoot-then-settle (ramp ~1.15 over the 320ms notice window, settle to 1.0 — a catch, not a swell).
- Stage cloud arrival as a 3-beat cascade off scene `uArrival` (p=1-uArrival): gate `arrivalLight` by `smoothstep(p - vAxis*0.5)` so roots/spine brighten before the body; cortex-local settle bloom at p~0.85 (`emissive *= 1 + ignite*exp(-((p-0.9)/0.06)^2)`).
- Wire the unused `openingTokens.nerveStaggerMs` so nerves light LAST.
- Points-path camera wake (`SuperbrainScene` 1885-1908): quint ease-out dolly-in that settles; autoRotate dips then resumes.
- Reduced-motion: cortex/luminance crossfade only, no camera travel, no spine inrush.

### 3. REABSORPTION — finished work's energy returns UP the spine, brain inhales  [high / large]  ✅ DONE (1ccd2dd)
Landed: travelling band (uReabsorbRise climb easeOutQuint 0.82s, dissolves into head) + cortex inhale (uReabsorbGlow flashBell peak ~1.0s, settle ~1.3s), latched one-shot on the reabsorbing rising edge; umbilical beads reverse (slab→spine) on retract; reduced-motion = cortex crossfade only. Dev scrub: `window.__REABSORB_PREVIEW=<s>`. (Operator to judge boldness of the band in live motion.)
One inward-terminating gesture across components:
- `uReabsorbGlow` drives a TRAVELING band (reuse reply-rise gaussian bead mechanic) climbing vAxis with ease-out decelerating into the cortex, not a static lobe.
- On arrival (center>0.85) bloom cortex with small overshoot then settle (the inhale), gated one-shot after the slab hands off.
- REVERSE umbilical bead direction during 'retracting' (pathT up toward spine) so visible energy stops contradicting the glow.
- `uFlow` brief up-surge overshoot (~300ms) synced to retract.
- Reduced-motion: cortex luminance crossfade only.

### 4. MULTI-FILE CASCADE — several panels bloom/reabsorb in sequence  [medium / large]  ✅ DONE (cheap-win, 4e63c45)
Landed the cheap win: REACH staggered by seat order (CASCADE_STAGGER_MS 110ms, focus leads, cap 6 → ≤660ms) so panels bloom 1→2→3; each unfurls normally as its reach lands. Single panels unchanged; reduced-motion = instant-live. (Larger per-vertebra addressed-bead version still open.)
- Cheap win first: pass `conductorOrder`/`waitingIndex` into MaterializedTab, offset elapsed by index*~90-120ms before reachProgress → panels bloom 1→2→3 (focus leads); cap total cascade ~600ms.
- Larger: publish per-active-tab `{axisSeat, energy, phase}` array from the tab store → feed point shader as a uniform array; sum addressed beads at each vertebra seat (down on materialize, up on reabsorb), staggered by order.
- Reduced-motion: zero stagger, straight to live/crossfade.

### 5. DISMISS / SETTLE — retract + return to REST (+ error / hold beats)  [medium / medium]  ✅ DONE (4e63c45 + 4556f99)
Landed the asymmetric retract (4e63c45): ~1.05 anticipation puff → Y folds shut FIRST (easeInCubic, gone ~74%) → x/z trail → horizontal sliver drunk up the cord; rim FLARES first ~20% then fades. Landed the emotional beats (4556f99): ERROR WINCE (uFlinch 2-3 decaying throbs on error onset, red rides posture tint), APPROVAL RELEASE (single uFlinch burst + uFlowSpeed overshoot when leaving approval_hold), REST EXHALE (uBreath half-sine dip on rest landing). Reduced-motion: soft single crossfade, no throb/dip. Idle byte-identical. DEFERRED: approval camera push (points camera is OrganismFraming, not cameraPush/CameraDrift).
- Asymmetric retract (the being DRINKING the panel back): ease-IN on position accelerating UP the curve; collapse Y before x/z (fold shut); ~1.04 anticipation puff + rim brighten at retract<0.1; hand off to reabsorption inhale.
- Authored release ramp before REST decay: ease `uPostureTint`/`uFlow` down on gentle ease-in over final ~600ms + breath exhale at rest landing.
- One-shot error flinch in the cloud (sinceError): scatter/uGrow micro-burst + 2-3 decaying red pulses ~600ms then settle.
- Approval-hold RELEASE asymmetric: one-shot uBurst + forward camera push + uFlow quint ease-out overshoot while uHold decays slower ~700ms.

## Ambient polish (lower priority, after signature moments)
- Reduced-motion luminance CROSSFADE (today snaps uniforms = hard cuts; split positional=instant / luminance=short crossfade).
- **CosmicBackground a11y bug (true defect, cheap):** starfield streams stars AT the camera (expanding optical flow = vestibular/migraine trigger) + takes NO reducedMotion prop → never gated. Pass reducedMotion, freeze/slow uTime. (`CosmicBackground.tsx`)
- Umbilical bead phase accumulation (accumulate `beadPhase += speed*delta` + damp beadFlowSpeed) → no teleport stutter on state change; gate main bead train under reduced-motion.
- Cauda tail retract: moving `uSprayFront` 0→1 ease-out (tips vanish first, front travels UP) + conus flick on full retract + slight overshoot on rest unfurl.
- Typewriter: replace 90ms metronome with ~120ms fade+rise per line, varying cadence (110→70ms), 2-3-line bursts, blinking cursor.
- Work-onset cascade: stage the 4 uniforms (vertebrae fast ~5 → state-pulse +150-250ms → body dim slower ~2 → tail last).
- DOM chrome: re-time `gagos-rise` (wordmark retired → dead 0.24s gap); memory-trail node ignite-before-text; dock-minimize ease + ack pulse; mic glow ease-in.
- Body-marks: phase-lock SupervisedMark breath to uBreath; ErrorScarMark = flinch not constant sine; AutoOrbitMark spins with work intensity; split brain gaze (fast) vs body (slower) lean with yaw overshoot.
