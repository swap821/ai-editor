# Deep Human Spine Structure — Codex Build Spec

**Date:** 2026-06-16
**Owner:** operator (kumarswapnil82)
**Author (planner):** Claude
**Writer:** Codex (sole frontend writer for this task)
**Base commit (hash-pin):** `16465da` on branch `feat/living-being-p1`
**Design provenance:** workflow `wf_58cdbe2b-0ca` (anatomy + pipeline-contract + shine-audit + 3 vertebra designs). Full research dump: `C:\Users\kumar\AppData\Local\Temp\claude\C--Users-kumar-ai-editor\...\tasks\wdyrmam0d.output`. This spec selects the **Layered-Detail** approach (operator-approved).

---

## 0. The goal in one line

Make the spine read as a **deep, complex, HUMAN** vertebral column (not abstract rings) — still luminous flesh wearing the brain's exact Voronoi material — and finish the **steady-glow** polish. The loved brain (cortex) is **untouchable**.

## 1. Current state you are building on (committed at `16465da`)

Already done — **do not redo, do not break**:
- `frontend/src/superbrain/lib/brainMaterial.ts` — `makeBrainMaterial({bodyMode})` factory. `cortex` path is **byte-identical to canon brain**. `nerve` path adds: fine Voronoi (`uNerveScale` default 24), contrast/glow/fresnel leaves, breath, `uFlow` impulse **gated by `uFlowGain`** (0 at rest → no strobe), growth (`uGrow` + `aBirth`).
- `frontend/src/superbrain/components/canvas/NervousSystem.tsx` — cord + vertebrae (torus rings) + roots + spray as **4 merged mesh bundles** (cord+stem / vertebrae / roots / spray), each wearing the one nerve material. Helpers: `makeTaperedTube(points, tubularSegs, radialSegs, radiusAt, birthFrom)`, `bakeNerveAttributes(geo, random, arcFn, hueJitter)`, `bakeBirthConstant(geo, point)`. Brainstem reshaped (`STEM_TOP_R` 0.42, `STEM_TOP_RISE` 0.55) to fill the brain's basal opening. Growth: `uGrow` front (auto-advance after `GROW_DELAY_S`=1.1s over `GROW_DURATION_S`=6.5s).
- `SuperbrainScene.tsx` — `BrainModel` builds its material via `makeBrainMaterial({tier, uniforms, nodeBrain})` (cortex). `NervousSystem` mounted with `tier`. Camera (`CameraDrift`) is canon (dev inspect hook already removed).

**The aesthetic is locked:** brain palette + shader, cord fine-stipple (scale 24), steady rest glow. Don't regress these.

## 2. Pipeline contract — MUST hold (from the pipeline audit)

1. **Every nerve geometry baked into a bundle MUST carry the identical attribute set:** `position`, `normal`, `uv`, `objectPos`, `color`, `aArc`, `aBirth`. `mergeGeometries(list, false)` requires all geos in one bundle to share the **same attribute names**. `TubeGeometry` (via `makeTaperedTube`) and `TorusGeometry` both emit `position/normal/uv`; `makeTaperedTube` also bakes `aBirth`; tori need `bakeBirthConstant(geo, anchor)` for `aBirth`; then `bakeNerveAttributes` adds `objectPos/color/aArc`. **Safety:** after building each sub-part, assert the attribute set matches before pushing; if `mergeGeometries` returns `null`, you have a mismatch — normalize (ensure all geos have exactly `{position,normal,uv,objectPos,color,aArc,aBirth}`; delete any stray attribute, add any missing). Add a `console.assert` during dev.
2. **`objectPos` = the RAW group-local vertex position** (unchanged after baking). This is the continuity contract: the brain shader samples `vLocalPos = objectPos * 2.0` so the Voronoi web flows unbroken from cord into every sub-part. Never offset/normalize `objectPos`.
3. **Growth contract:** a part is born when the `uGrow` front passes its `aArc`. `born = smoothstep(0, 0.12, uGrow - aArc)`, `transformed = mix(aBirth, position, born)`, emission faded by `born`. So:
   - every sub-part of vertebra `i` MUST share **one `aArc` = `segArc` = `0.05 + f*0.7`** (`f = i/(SEGMENT_COUNT-1)`), and
   - every sub-part MUST set **`aBirth` = that vertebra's spine anchor** (`new THREE.Vector3(anchor.x, anchor.y, anchor.z)`), so the **whole vertebra blooms from the spine as one unit**.
   - swept parts pass the anchor as `makeTaperedTube(..., birthFrom = anchorClone)` (NOT `'centerline'`), so the arm unfurls OUT from the spine.
4. **Draw-call budget = 4** (cord+stem / vertebrae / roots / spray). All new vertebra sub-parts go into the **vertebrae bundle** (one `mergeGeometries`). No new mesh nodes, no new material.
5. **FIDELITY:** all changes gated to the `nerve` path / `isNerve` / `bodyMode==='nerve'`. **Never touch the cortex path** — the brain must stay byte-identical (existing goldens hold).

---

## 3. TASK A — Deep human vertebrae (Layered-Detail) — PRIMARY

Replace the bare torus rings with the five human cues, **per `SEGMENT_ANCHORS[i]`**, all in the existing `SEGMENT_ANCHORS.forEach` loop in `NervousSystem.tsx`. Reuse `f`, `segArc`, `anchor`. Coordinate frame: group-local, cord descends `-Y`, bows in `±Z`; **rear/posterior = `-Z`** (behind the cord), anterior = `+Z`. `CORD_Z = -0.42`.

**New tunables** (add near the other vertebra tunables, ~line 113):
```
const SPINOUS_LEN_TOP = 0.11, SPINOUS_LEN_BOT = 0.15, SPINOUS_R = 0.020;
const TRANSVERSE_LEN_TOP = 0.085, TRANSVERSE_LEN_BOT = 0.12, TRANSVERSE_R = 0.018;
const DISC_TUBE = 0.018, DISC_R_SCALE = 1.12;
const PROC_TUBE_SEGMENTS = 14, PROC_RADIAL_SEGMENTS = 8;
```

**A1 — Keep the centrum rings.** The existing `VERTEBRA_GIRTH=2` stacked tori stay (the loved crisp body band). New parts are ADDED in the same loop.

**A2 — Lumbar girth swell (1 line, body-progression cue).** Where the ring major radius is computed (`ringR = lerp(VERTEBRA_RING_TOP_R, VERTEBRA_RING_BOTTOM_R, f)`), profile it so lumbar bodies fatten:
```
const bodyR = ringR * (1.0 + 0.35 * THREE.MathUtils.smoothstep(f, 0.55, 1.0));
```
Use `bodyR` as the torus major radius. (Cervical unchanged, lumbar third swells → inverted-teardrop column.)

**A3 — Intervertebral disc** (cue: soft segmentation). For each segment except the last, a thin flat torus midway to the next body:
```
const discY = (anchor.y + SEGMENT_ANCHORS[i+1].y) * 0.5;
const disc = new THREE.TorusGeometry(bodyR * DISC_R_SCALE, DISC_TUBE, PROC_RADIAL_SEGMENTS, VERTEBRA_TUBULAR_SEGMENTS);
disc.rotateX(Math.PI/2);
disc.translate(anchor.x, discY, anchor.z);
bakeBirthConstant(disc, new THREE.Vector3(anchor.x, anchor.y, anchor.z));
bakeNerveAttributes(disc, random, () => segArc + (random()-0.5)*0.01, 0.04);
```
Wider (`DISC_R_SCALE`) + much thinner (`DISC_TUBE` vs ring tube 0.045) → reads as a glowing cushion, not bone.

**A4 — Spinous process** (cue: THE saw-tooth spur that says "vertebra"). One posterior (`-Z`) tapered tube per segment, with a per-zone downward tilt — upright cervical → roof-shingle thoracic → blunt lumbar:
```
const spLen = THREE.MathUtils.lerp(SPINOUS_LEN_TOP, SPINOUS_LEN_BOT, f);
const tilt = THREE.MathUtils.lerp(0.15, 0.85, THREE.MathUtils.smoothstep(f, 0.15, 0.55))
           * (1.0 - 0.5 * THREE.MathUtils.smoothstep(f, 0.75, 1.0)); // peak thoracic, ease lumbar
const p0 = new THREE.Vector3(anchor.x, anchor.y, anchor.z - ringR*0.2);
const p1 = new THREE.Vector3(anchor.x, anchor.y - spLen*tilt*0.4, anchor.z - ringR - spLen*0.45);
const p2 = new THREE.Vector3(anchor.x, anchor.y - spLen*tilt,     anchor.z - ringR - spLen*0.95);
const spine = makeTaperedTube([p0,p1,p2], PROC_TUBE_SEGMENTS, PROC_RADIAL_SEGMENTS,
  (t) => SPINOUS_R * (1.0 - 0.55*t), new THREE.Vector3(anchor.x, anchor.y, anchor.z));
bakeNerveAttributes(spine, random, () => segArc + (random()-0.5)*0.012, 0.05);
```
Tapers to a point at the tip; births from the anchor.

**A5 — Transverse processes** (cue: bilateral wings). Left+right short tapered tubes from the body, lateral in all zones, swept FORWARD (`+Z`) in thoracic for the rib-mount angle:
```
const tpLen = THREE.MathUtils.lerp(TRANSVERSE_LEN_TOP, TRANSVERSE_LEN_BOT, f);
const fwd = 0.06 * THREE.MathUtils.smoothstep(f, 0.2, 0.55) * (1.0 - THREE.MathUtils.smoothstep(f, 0.7, 1.0));
for (const side of [-1, 1] as const) {
  const q0 = new THREE.Vector3(anchor.x, anchor.y, anchor.z);
  const q1 = new THREE.Vector3(side*tpLen*0.5, anchor.y + 0.01,  anchor.z + fwd*0.5);
  const q2 = new THREE.Vector3(side*tpLen,     anchor.y + 0.005, anchor.z + fwd);
  const tp = makeTaperedTube([q0,q1,q2], PROC_TUBE_SEGMENTS, PROC_RADIAL_SEGMENTS,
    (t) => TRANSVERSE_R * (0.7 + 0.5*t), new THREE.Vector3(anchor.x, anchor.y, anchor.z));
  bakeNerveAttributes(tp, random, () => segArc + (random()-0.5)*0.012, 0.05);
  vertebraGeos.push(tp);
}
```

**A6 — Push order + single merge.** Per segment push: the 2 centrum rings (existing) → disc (if not last) → spinous → 2 transverse. After the loop, the existing `mergeGeometries(vertebraGeos, false)` folds all (~52 geos) into the SAME `vertebraeBundle` → **still 1 draw call**. Keep the existing `vertebraGeos.forEach(g => g.dispose())` cleanup.

**A7 — Merge safety (the footgun).** Tori and tubes must share the identical attribute set for the merge. Both emit `position/normal/uv`; both get `aBirth` (tori via `bakeBirthConstant`, tubes via `makeTaperedTube`'s `birthFrom`) and then `objectPos/color/aArc` via `bakeNerveAttributes`. Verify `mergeGeometries(...)` is non-null. If it's null, add a `normalizeNerveAttrs(geo)` that guarantees exactly `{position,normal,uv,objectPos,color,aArc,aBirth}` on every geo (delete extras, add missing) and apply it to ALL vertebra geos (including the centrum rings) before pushing.

**The neural arch / spinal canal** are intentionally *implied* (the spinous + transverse cluster reads as the posterior framework; the canal = the lit cord through the ring centers). No dedicated mesh — composition over CAD detail. If the operator's browser read is too sparse, a small rear bracket torus can be added later as one more sub-part.

---

## 4. TASK B — 110% texture (two-octave parity)

Currently the nerve runs **single-octave** Voronoi (`webOctaves: 1`) for perf; the brain runs **two-octave** on high tier. To match the brain exactly:
1. In the `NervousSystem.tsx` `makeBrainMaterial({...})` call, change `webOctaves: 1` → `webOctaves: 'tier'` (2-octave on high tier, 1 elsewhere). The cache key already includes octaves, so it recompiles cleanly.
2. **Verify perf** on the operator's machine (the nerve also uses an 8-cell neighbourhood, so this is cheaper than the cortex's 27-cell 2-octave). If high-tier fps dips at 1080p, fall back to `1` and instead nudge contrast (`uNerveContrastLo`/`Hi`) for crispness. Report the fps you observe.
3. Do not change the cortex octaves.

---

## 5. TASK C — Final shine / flow polish

- **DONE (keep):** the impulse flow-band is gated by `uFlowGain` (0 at rest). The cord glows steady at rest; the impulse only travels on cognition activity. Verified live.
- **WATCH (only if the operator still sees a rim throb):** the fresnel pulse `sin(uTime*2.0)` (~3.1s rim breath) is in the **shared** emission ladder. If the nerve rim throbs distractingly, add an `isNerve` branch that uses a **calmer** pulse for the nerve only (e.g. swing 0.95→1.15 instead of 0.7→1.5), and **leave the cortex line byte-identical**. Do NOT slow/alter the cortex pulse (FIDELITY / goldens).
- **Growth hot-line** (`growEdge`) only fires while `uGrow < 1` — leave as is.

---

## 6. Constraints / gates (non-negotiable)

- Cortex/brain path **byte-identical**. All edits gated to nerve / `isNerve` / `bodyMode==='nerve'`.
- **4 draw calls** max. New vertebra detail stays in the vertebrae bundle.
- Growth + continuity contracts (§2.2, §2.3) preserved — new parts bloom from the spine as one and sample `objectPos` raw.
- Green before handoff: `cd frontend && npm run typecheck` (clean) and `npm test` (128/128; add tests if you introduce testable logic).
- **Final aesthetic = operator's browser.** Do not declare "done" — hand to Claude for review, operator judges the look.

## 7. Browser verification (for your self-check before handoff)

The dev scrub hooks were removed for the clean base. If you need to verify the growth/stages, you may TEMPORARILY re-add a `window.__GROW` override in the `NervousSystem` `useFrame` (the pattern: `const o = window.__GROW; NERVE_GROW_UNIFORM.value = (o ?? autoGrow)`), screenshot, then **remove it before handoff**. Check:
1. Vertebrae read **human**: spinous spurs clearly visible, tilt changes cervical→thoracic→lumbar, bilateral wings present, discs between bodies.
2. Each vertebra **blooms as one** from the spine during growth (rings + spurs + wings + disc inflate together).
3. **Steady glow** at rest (no per-second strobe).
4. **4 draw calls** (R3F perf HUD).
5. **Brain unchanged** vs `16465da`.

## 8. Handoff protocol

- One writer = **Codex** on this task. Claim the worktree lease, implement §3→§4→§5 (in that priority order), run gates, then hand to **Claude** for diff + gate review; operator judges the look in-browser.
- If you hit a design ambiguity, **do NOT invent** — leave a `// CLAUDE?:` comment and flag it in handoff rather than guessing.
- Base is pinned at `16465da`. If that moves, re-sync before writing.
