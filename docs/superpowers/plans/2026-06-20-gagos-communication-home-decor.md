# GAGOS Communication Surface + Home Decor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unprofessional conversation UI on the point-field being with an entirely in-world (no-DOM) communication surface and a restrained "home" framing: a camera-anchored GAGOS / live-LLM / supervised readout, the being's reply materialized on a vertebra-seated slab, a diegetic intake organ, slow voyaging drift, a points-tuned vignette, and a dialed horizon glow.

**Architecture:** Reuse the proven materialization stack — the reply rides the existing `content` slab path (`MaterializedTab` + `tabStore.showContentSurface` + `materializedSurfaceAnchors`) via a thin `showReplySurface` wrapper; the GAGOS readout is a 3D text group parented to the drei `PerspectiveCamera` so it holds the top-left corner through orbit and still passes through the existing Bloom. Home decor reuses the existing `Vignette` pass (points variant) + OrbitControls `autoRotate` + one new faint `HorizonGlow` element. Pure logic (reply writer, active-LLM formatter) is TDD'd; shader/visual units are smoke-tested and gated live at `:5173`.

**Tech Stack:** React Three Fiber, three.js, @react-three/drei (`Text`, `PerspectiveCamera`, `OrbitControls`), @react-three/postprocessing (`Vignette`), Vitest. Spectral-v1 palette (sacred).

**Spec:** `docs/superpowers/specs/2026-06-20-gagos-communication-home-design.md`

---

## Ground rules (apply to EVERY task)

- **Test on `:5173` only** — `:5173/?ui=superbrain&being=points`. Backend CORS allows `:5173/:4173/:3000`; other ports fail silently.
- **Palette + textures are SACRED.** Every new luminous element reuses spectral-v1 tones (violet `#6a35ff`, cyan `#19d4f0`, the warm reply tone `#ffe3a8`). Invent no new colors. Final color/intensity is the operator's `:5173` call.
- **Mirror discipline.** Files under `frontend/src/superbrain/*` MUST be copied to the lab (`GAG demo/gag-orchestrator/src/...`, same relative path as prior phases). `frontend/src/workbench/BrainstemIntake.jsx` is **product-only — do NOT mirror it.**
- **Commits:** commit after each task with an explicit pathspec (the working tree has unrelated staged deletions + junk; never `git add -A`). End every commit message with the `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` trailer.
- **No push.** Landing/pushing is a separate operator decision.
- Keep `npm test` (currently 284 passing), `npm run typecheck`, and `npm run lint` green throughout. Commands run from `frontend/`.

---

## File structure

| File | Responsibility | Mirror? |
| --- | --- | --- |
| `frontend/src/superbrain/lib/tabStore.ts` | + `REPLY_FILEPATH`, `showReplySurface()` (wraps `showContentSurface`) | yes |
| `frontend/src/superbrain/lib/tabStore.test.ts` | reply-writer unit tests | yes |
| `frontend/src/superbrain/components/canvas/MaterializedTab.tsx` | reply slab reads as the being (header `GAGOS`, no code footer) | yes |
| `frontend/src/superbrain/lib/activeBrain.ts` | live active-LLM store + `formatActiveBrainLine()` | yes |
| `frontend/src/superbrain/lib/activeBrain.test.ts` | formatter unit tests | yes |
| `frontend/src/superbrain/components/canvas/IdentityReadout.tsx` | GAGOS + LLM + supervised, camera-anchored 3D text | yes |
| `frontend/src/superbrain/components/canvas/HorizonGlow.tsx` | one faint distant luminous band | yes |
| `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` | mount readout (camera child) + horizon; OrbitControls `autoRotate` | yes |
| `frontend/src/superbrain/components/canvas/PostFX.tsx` | points-mode vignette variant | yes |
| `frontend/src/superbrain/lib/constants.ts` | `POST_FX.vignettePoints` | yes |
| `frontend/src/workbench/BrainstemIntake.jsx` | route reply→slab, remove floating billboard, intake organ + invitation | **NO (product-only)** |

---

## Task 1: `showReplySurface` writer in tabStore (TDD)

**Files:**
- Modify: `frontend/src/superbrain/lib/tabStore.ts`
- Test: `frontend/src/superbrain/lib/tabStore.test.ts` (create if absent)

- [ ] **Step 1: Write the failing test**

Add to `tabStore.test.ts` (if the file does not exist, create it with this content):

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import {
  showReplySurface,
  REPLY_FILEPATH,
  getMaterializedTabByKind,
  getTabStoreSnapshot,
  __resetTabStoreForTests,
} from './tabStore';

describe('showReplySurface', () => {
  beforeEach(() => __resetTabStoreForTests());

  it('materializes the reply as a content tab tagged with REPLY_FILEPATH', () => {
    const tab = showReplySurface('Main theek hoon.', { seatIndex: 2 });
    expect(tab.kind).toBe('content');
    expect(tab.content?.filepath).toBe(REPLY_FILEPATH);
    expect(tab.content?.code).toBe('Main theek hoon.');
    expect(tab.seatIndex).toBe(2);
    expect(getMaterializedTabByKind('content')?.id).toBe(tab.id);
  });

  it('updates the SAME tab on a follow-up reply (no duplicate slabs)', () => {
    const first = showReplySurface('one', { seatIndex: 2 });
    const second = showReplySurface('one two', { seatIndex: 2 });
    expect(second.id).toBe(first.id);
    expect(second.content?.code).toBe('one two');
    expect(getTabStoreSnapshot().tabs.filter((t) => t.content?.filepath === REPLY_FILEPATH)).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Run the test, verify it fails**

Run: `npm test -- tabStore`
Expected: FAIL — `showReplySurface`/`REPLY_FILEPATH` are not exported.

- [ ] **Step 3: Implement the writer**

In `tabStore.ts`, after `showContentSurface` (ends line ~250), add:

```ts
/** Sentinel filepath that marks a content surface as the being's spoken reply
 *  (so MaterializedTab renders it as the being's voice, not a code file). */
export const REPLY_FILEPATH = 'gagos://reply';

/** The being's reply, materialized on the existing vertebra-seated content slab.
 *  Reuses showContentSurface so the slab unfurl/retract + line-by-line reveal
 *  ("speaking") come for free; the REPLY_FILEPATH sentinel re-skins the chrome. */
export function showReplySurface(
  text: string,
  options: {
    bornAt?: number;
    originLocal?: [number, number, number];
    targetLocal?: [number, number, number];
    seatIndex?: number | null;
  } = {},
): MaterializedTabRecord {
  return showContentSurface({ code: text, language: '', filepath: REPLY_FILEPATH }, options);
}
```

- [ ] **Step 4: Run the test, verify it passes**

Run: `npm test -- tabStore`
Expected: PASS (both cases).

- [ ] **Step 5: Mirror + commit**

Copy the two changed files to the lab (same relative path under `GAG demo/gag-orchestrator/src/`).

```bash
git add -- frontend/src/superbrain/lib/tabStore.ts frontend/src/superbrain/lib/tabStore.test.ts
git commit -m "feat(gagos): showReplySurface — reply rides the content slab

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Reply slab reads as the being (MaterializedTab chrome)

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/MaterializedTab.tsx` (functions `getSurfaceHeader` ~line 211, `getSurfaceFooter` ~line 223)

The content slab normally shows a filename header and language footer. For the reply sentinel, show the being's name and no code footer. The line-by-line reveal (gated on `tab.kind === 'content'`, line ~1462) already applies — that becomes the "speaking" effect, no change needed.

- [ ] **Step 1: Import the sentinel**

At the top of `MaterializedTab.tsx`, add `REPLY_FILEPATH` to the existing `tabStore` import (the import that already brings in `MaterializedTabRecord`, `MaterializedApprovalSurface`, etc.):

```ts
import { /* …existing… */ REPLY_FILEPATH } from '@/lib/tabStore';
```

(If `MaterializedTab` imports tabStore types via a type-only import, add a separate value import: `import { REPLY_FILEPATH } from '@/lib/tabStore';`.)

- [ ] **Step 2: Branch the header**

In `getSurfaceHeader`, make the `content` branch (line ~212) recognize the reply:

```ts
function getSurfaceHeader(tab: MaterializedTabRecord): string {
  if (tab.kind === 'content') {
    if (tab.content?.filepath === REPLY_FILEPATH) return 'GAGOS';
    return tab.content?.filepath ? baseName(tab.content.filepath) : 'materialized tab';
  }
  // …unchanged…
```

- [ ] **Step 3: Branch the footer**

In `getSurfaceFooter`, content branch (line ~224):

```ts
function getSurfaceFooter(tab: MaterializedTabRecord): string {
  if (tab.kind === 'content') {
    if (tab.content?.filepath === REPLY_FILEPATH) return '';
    return tab.content?.language ?? 'text';
  }
  // …unchanged…
```

- [ ] **Step 4: Typecheck**

Run: `npm run typecheck`
Expected: PASS (no type errors).

- [ ] **Step 5: Mirror + commit**

Copy `MaterializedTab.tsx` to the lab.

```bash
git add -- frontend/src/superbrain/components/canvas/MaterializedTab.tsx
git commit -m "feat(gagos): reply slab reads as the being (GAGOS header, no code footer)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Route the reply through the slab; delete the floating billboard (product-only)

**Files:**
- Modify: `frontend/src/workbench/BrainstemIntake.jsx`

Goal: every place that currently sets `replyText` for the *billboard* instead drives the reply *slab*; the floating `<Billboard ref={replyBillboardRef}>` (lines ~712–729) and its `useFrame` block (lines ~604–608) are removed. The reply retracts on the existing `REPLY_DWELL_MS` timer and on a new turn.

- [ ] **Step 1: Add imports + a reply-tab ref**

At the top imports, add the writer + placement helpers + retract:

```jsx
import { showReplySurface } from '../superbrain/lib/tabStore';
import {
  getContentSurfacePlacement,
  selectNextAvailableVertebraSeat,
} from '../superbrain/lib/materializedSurfaceAnchors';
import { getOccupiedVertebraSeats } from '../superbrain/lib/tabStore';
```

(`beginRetractingMaterializedTab`, `getMaterializedTabByKind`, `upsertInputSurface`, `useTabStore` are already imported — keep them.)

Inside the component, near the other refs (~line 110), add:

```jsx
const replyTabIdRef = useRef(null);
```

- [ ] **Step 2: Add a helper that pushes the reply onto a vertebra slab**

Add this `useCallback` inside the component (after `submitTurn` or near it):

```jsx
const materializeReply = useCallback((text) => {
  const clean = clampSceneText(text, 220);
  if (!clean) return;
  const seat =
    replyTabIdRef.current == null
      ? selectNextAvailableVertebraSeat(getOccupiedVertebraSeats())
      : undefined;
  const placement = getContentSurfacePlacement(seat);
  const tab = showReplySurface(clean, placement);
  replyTabIdRef.current = tab.id;
}, []);

const retractReply = useCallback(() => {
  if (replyTabIdRef.current) {
    beginRetractingMaterializedTab(replyTabIdRef.current);
    replyTabIdRef.current = null;
  }
}, []);
```

- [ ] **Step 3: Drive the slab from the turn instead of the billboard**

In `submitTurn`, replace the three `if (showSceneConversation) setReplyText(...)` sites (streaming chunk ~line 230, post-stream ~line 244, and the visibleReply block) so they ALSO materialize the slab. Keep `setReplyText` (it still owns the dwell timer), and add the slab call right beside each:

```jsx
// in handleReplyChunk:
if (showSceneConversation) {
  setReplyText(chunkReply);
  materializeReply(chunkReply);
}
```
```jsx
// in the final visibleReply block:
if (showSceneConversation) {
  setReplyText(visibleReply);
  materializeReply(visibleReply);
}
```

At the very start of a turn, retract any prior reply slab — in `submitTurn`, right after `setReplyText('')` (~line 197):

```jsx
setReplyText('');
retractReply();
```

- [ ] **Step 4: Retract the slab when the reply dwell expires**

Change the reply-dwell effect (~lines 338–344) so it also retracts the slab:

```jsx
useEffect(() => {
  if (!replyText) return undefined;
  const reply = window.setTimeout(() => {
    if (!busyRef.current) {
      setReplyText('');
      retractReply();
    }
  }, REPLY_DWELL_MS);
  return () => window.clearTimeout(reply);
}, [replyText, retractReply]);
```

- [ ] **Step 5: Remove the floating reply billboard + its frame animation**

Delete the entire `{replyText ? (<Billboard ref={replyBillboardRef} …>…</Billboard>) : null}` JSX block (~lines 712–729). Delete the `replyBillboardRef` declaration (~line 94) and its `useFrame` block (~lines 604–608). Leave the intake/prompt billboard and the status billboard intact.

- [ ] **Step 6: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: PASS. (No unused `replyBillboardRef`.)

- [ ] **Step 7: Live fidelity check (operator gate)**

At `:5173/?ui=superbrain&being=points`: speak/type to the being. Expected: the reply unfurls on a slab from a vertebra, **to the side**, never over the brain or spine, line-reveals as it "speaks", header reads `GAGOS`, then retracts after the dwell. No floating smeared text remains.

- [ ] **Step 8: Commit (product-only — do NOT mirror)**

```bash
git add -- frontend/src/workbench/BrainstemIntake.jsx
git commit -m "feat(gagos): reply materializes on a vertebra slab; remove floating billboard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Active-LLM store + formatter (TDD)

**Files:**
- Create: `frontend/src/superbrain/lib/activeBrain.ts`
- Test: `frontend/src/superbrain/lib/activeBrain.test.ts`

The `route` cognition event carries `{ provider, model, privacy }`. This module keeps the latest value (so the readout shows the current brain at rest, not only mid-turn) and formats one line.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import {
  formatActiveBrainLine,
  getActiveBrain,
  setActiveBrain,
  __resetActiveBrainForTests,
} from './activeBrain';

describe('formatActiveBrainLine', () => {
  it('renders "Model · privacy"', () => {
    expect(formatActiveBrainLine({ model: 'Opus 4.8', privacy: 'cloud' })).toBe('Opus 4.8 · cloud');
  });
  it('falls back to provider when model is missing', () => {
    expect(formatActiveBrainLine({ provider: 'ollama', privacy: 'local' })).toBe('ollama · local');
  });
  it('shows a sensible default when nothing is known', () => {
    expect(formatActiveBrainLine({})).toBe('auto');
  });
});

describe('active brain store', () => {
  beforeEach(() => __resetActiveBrainForTests());
  it('starts at the default and updates on setActiveBrain', () => {
    expect(getActiveBrain().model).toBeUndefined();
    setActiveBrain({ model: 'Llama 3.1', privacy: 'local' });
    expect(getActiveBrain().model).toBe('Llama 3.1');
  });
});
```

- [ ] **Step 2: Run, verify fail**

Run: `npm test -- activeBrain`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```ts
export interface ActiveBrain {
  provider?: string;
  model?: string;
  privacy?: string;
}

let active: ActiveBrain = {};
const listeners = new Set<() => void>();

export function getActiveBrain(): ActiveBrain {
  return active;
}

export function setActiveBrain(next: ActiveBrain): void {
  active = { ...next };
  for (const l of listeners) {
    try { l(); } catch { /* one bad listener never breaks the rest */ }
  }
}

export function subscribeActiveBrain(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

/** One compact line for the GAGOS readout, e.g. "Opus 4.8 · cloud". */
export function formatActiveBrainLine(brain: ActiveBrain): string {
  const name = (brain.model || brain.provider || '').trim();
  const privacy = (brain.privacy || '').trim().toLowerCase();
  if (!name) return 'auto';
  return privacy ? `${name} · ${privacy}` : name;
}

export function __resetActiveBrainForTests(): void {
  active = {};
  listeners.clear();
}
```

- [ ] **Step 4: Run, verify pass**

Run: `npm test -- activeBrain`
Expected: PASS.

- [ ] **Step 5: Mirror + commit**

Copy both files to the lab.

```bash
git add -- frontend/src/superbrain/lib/activeBrain.ts frontend/src/superbrain/lib/activeBrain.test.ts
git commit -m "feat(gagos): active-brain store + line formatter

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: GAGOS identity readout (camera-anchored 3D text)

**Files:**
- Create: `frontend/src/superbrain/components/canvas/IdentityReadout.tsx`
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` (points-mode camera, ~line 1575)

The readout is rendered as a CHILD of the drei `PerspectiveCamera`, so it travels with the camera and stays pinned top-left through orbit, and (being in the main scene) blooms like the body. It subscribes to `route` events (updates the model line) and `voice-speaking` (dims while the being talks).

- [ ] **Step 1: Create the component**

```tsx
'use client';

import { useEffect, useRef, useState } from 'react';
import { Text } from '@react-three/drei';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { subscribeCognition } from '@/lib/cognitionBus';
import {
  getActiveBrain,
  setActiveBrain,
  subscribeActiveBrain,
  formatActiveBrainLine,
} from '@/lib/activeBrain';

// View-space anchor: child of the camera, so this is metres in front of the lens.
// Tuned for the points-mode fov=26 camera; operator fine-tunes via window.__GAGOS.
const ANCHOR = { x: -1.92, y: 1.12, z: -4 };

const NAME_COLOR = new THREE.Color('#cdbbff'); // spectral violet, lifted for legibility
const META_COLOR = new THREE.Color('#7fe9ff'); // spectral cyan
const DOT_COLOR = new THREE.Color('#9b6bff');

export default function IdentityReadout({ name = 'GAGOS', supervised = true }) {
  const groupRef = useRef(null);
  const [modelLine, setModelLine] = useState(() => formatActiveBrainLine(getActiveBrain()));
  const speakingRef = useRef(0); // 0..1, decays; dims the cluster while speaking

  useEffect(() => subscribeActiveBrain(() => setModelLine(formatActiveBrainLine(getActiveBrain()))), []);

  useEffect(
    () =>
      subscribeCognition((event) => {
        if (event.type === 'route' && event.data) {
          setActiveBrain({
            provider: event.data.provider,
            model: event.data.model,
            privacy: event.data.privacy,
          });
        }
        if (event.type === 'voice-speaking') speakingRef.current = 1;
      }),
    [],
  );

  useFrame((_s, delta) => {
    speakingRef.current = Math.max(0, speakingRef.current - delta * 0.6);
    if (typeof window !== 'undefined' && window.__GAGOS) {
      const d = window.__GAGOS;
      if (groupRef.current) groupRef.current.position.set(d.x ?? ANCHOR.x, d.y ?? ANCHOR.y, d.z ?? ANCHOR.z);
    }
    if (groupRef.current) {
      // dim ~35% while speaking so it never competes with the reply slab.
      const dim = 1 - speakingRef.current * 0.35;
      groupRef.current.traverse((o) => {
        if (o.material && 'opacity' in o.material) o.material.opacity = dim;
      });
    }
  });

  return (
    <group ref={groupRef} position={[ANCHOR.x, ANCHOR.y, ANCHOR.z]}>
      <Text fontSize={0.2} anchorX="left" anchorY="top" color={NAME_COLOR.getStyle()}
            outlineWidth={0.006} outlineColor="#05010f" letterSpacing={0.18}
            material-toneMapped={false} material-transparent>
        {name}
      </Text>
      <group position={[0, -0.28, 0]}>
        <mesh position={[0.05, 0, 0]}>
          <circleGeometry args={[0.028, 16]} />
          <meshBasicMaterial color={DOT_COLOR} toneMapped={false} transparent />
        </mesh>
        <Text position={[0.14, 0.02, 0]} fontSize={0.085} anchorX="left" anchorY="top"
              color={META_COLOR.getStyle()} outlineWidth={0.004} outlineColor="#031016"
              material-toneMapped={false} material-transparent>
          {modelLine}
        </Text>
      </group>
      {supervised ? (
        <Text position={[0, -0.46, 0]} fontSize={0.07} anchorX="left" anchorY="top"
              color="#8aa0b8" outlineWidth={0.003} outlineColor="#02080d"
              letterSpacing={0.08} material-toneMapped={false} material-transparent>
          supervised
        </Text>
      ) : null}
    </group>
  );
}
```

- [ ] **Step 2: Mount it as a child of the points-mode camera**

In `SuperbrainScene.tsx`, import it near the other canvas imports:

```tsx
import IdentityReadout from './IdentityReadout';
```

Change the self-closing points-mode `PerspectiveCamera` (~line 1575) to wrap the readout:

```tsx
<PerspectiveCamera makeDefault fov={26} near={0.1} far={100} position={[0, -0.5, 15]}>
  <IdentityReadout />
</PerspectiveCamera>
```

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Live fidelity check**

At `:5173/?being=points`: top-left shows `GAGOS`, a model line (updates after you send a turn — watch it change to the routed model), and `supervised`. It stays in the corner while you orbit, and glows (blooms). It dims slightly while the being is replying. Tune position live with `window.__GAGOS = { x: -1.9, y: 1.1, z: -4 }`.

- [ ] **Step 5: Mirror + commit**

Copy `IdentityReadout.tsx` and `SuperbrainScene.tsx` to the lab.

```bash
git add -- frontend/src/superbrain/components/canvas/IdentityReadout.tsx frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(gagos): camera-anchored GAGOS / LLM / supervised readout

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Voyaging drift (slow OrbitControls auto-rotate)

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` (points-mode `OrbitControls`, ~line 1576)

A very slow auto-rotate reads as the observer drifting around the being in deep space; manual orbit still works and resumes the drift when idle.

- [ ] **Step 1: Add a dialable speed constant**

Near the top of `SuperbrainScene.tsx` constants (by `BRAIN_SCALE`, ~line 60), add:

```tsx
// Restrained "voyaging" — a slow auto-orbit; operator tunes live via window.__GAGOS.voyage.
const VOYAGE_SPEED = 0.18;
```

- [ ] **Step 2: Enable autoRotate on the points-mode controls**

Add the two props to the points-mode `<OrbitControls>` (keep the existing `makeDefault`, `enablePan={false}`, `target`):

```tsx
<OrbitControls
  makeDefault
  enablePan={false}
  target={[0, -0.5, 0]}
  autoRotate
  autoRotateSpeed={VOYAGE_SPEED}
/>
```

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Live fidelity check**

At `:5173/?being=points`: the view slowly drifts around the being; dragging orbits manually and the drift resumes. If too fast/slow, the operator adjusts `autoRotateSpeed` (try 0.10–0.30).

- [ ] **Step 5: Mirror + commit**

```bash
git add -- frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(gagos): restrained voyaging auto-orbit in points mode

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Points-mode vignette (home framing)

**Files:**
- Modify: `frontend/src/superbrain/lib/constants.ts` (`POST_FX`, ~line 220)
- Modify: `frontend/src/superbrain/components/canvas/PostFX.tsx` (~line 200)

- [ ] **Step 1: Add the points variant constant**

In `constants.ts`, beside `vignette`:

```ts
vignette: { offset: 0.28, darkness: 0.62 },
// Points being frames the void a touch more strongly to read as a "home".
vignettePoints: { offset: 0.32, darkness: 0.76 },
```

- [ ] **Step 2: Select it in points mode**

In `PostFX.tsx`, beside the existing `bloom` selection (~line 152):

```tsx
const vignette = readBeingMode() === 'points' ? POST_FX.vignettePoints : POST_FX.vignette;
```

Then use it in the `<Vignette>` element (~line 200):

```tsx
<Vignette
  offset={vignette.offset}
  darkness={vignette.darkness}
  blendFunction={BlendFunction.NORMAL}
/>
```

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Live fidelity check**

At `:5173/?being=points`: edges are gently darker, framing the being; the top-left readout is still fully legible (if corners crush the text, lower `darkness` toward 0.70).

- [ ] **Step 5: Mirror + commit**

```bash
git add -- frontend/src/superbrain/lib/constants.ts frontend/src/superbrain/components/canvas/PostFX.tsx
git commit -m "feat(gagos): points-mode vignette frames the home void

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Horizon glow (one faint distant band)

**Files:**
- Create: `frontend/src/superbrain/components/canvas/HorizonGlow.tsx`
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` (points block, near the brain mount)

A single wide, soft, additive band low and far behind the being — depth without clutter. Default opacity is low; operator dials via `window.__GAGOS.horizon`.

- [ ] **Step 1: Create the component**

```tsx
'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';

// A wide, soft vertical-gradient band; additive, faint, far behind the being.
const VERT = /* glsl */ `
  varying vec2 vUv;
  void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }
`;
const FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform vec3 uColor;
  uniform float uOpacity;
  void main() {
    // brightest at the horizon line (vUv.y ~ 0.5), fading up and down.
    float band = exp(-pow((vUv.y - 0.5) / 0.16, 2.0));
    float sides = smoothstep(0.0, 0.35, vUv.x) * smoothstep(1.0, 0.65, vUv.x);
    float a = band * mix(0.5, 1.0, sides) * uOpacity;
    gl_FragColor = vec4(uColor * a, a);
  }
`;

export default function HorizonGlow({ color = '#3a1f7a', opacity = 0.16 }) {
  const matRef = useRef(null);
  useFrame(() => {
    if (typeof window !== 'undefined' && window.__GAGOS && matRef.current) {
      const o = window.__GAGOS.horizon;
      if (typeof o === 'number') matRef.current.uniforms.uOpacity.value = o;
    }
  });
  return (
    <mesh position={[0, -3.2, -10]} renderOrder={0} frustumCulled={false}>
      <planeGeometry args={[60, 14, 1, 1]} />
      <shaderMaterial
        ref={matRef}
        vertexShader={VERT}
        fragmentShader={FRAG}
        transparent
        depthWrite={false}
        depthTest={false}
        toneMapped={false}
        blending={THREE.AdditiveBlending}
        uniforms={{
          uColor: { value: new THREE.Color(color) },
          uOpacity: { value: opacity },
        }}
      />
    </mesh>
  );
}
```

- [ ] **Step 2: Mount it in the points block**

In `SuperbrainScene.tsx`, import it:

```tsx
import HorizonGlow from './HorizonGlow';
```

Inside the `BEING_MODE === 'points'` JSX region (the same block as the points camera/being, ~line 1570), add as a sibling of the being:

```tsx
{BEING_MODE === 'points' && <HorizonGlow />}
```

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck`
Expected: PASS.

- [ ] **Step 4: Live fidelity check**

At `:5173/?being=points`: a faint luminous band sits low behind the being, adding depth without re-cluttering the void. Tune with `window.__GAGOS = { horizon: 0.10 }` (0 = off). If it reads as "fog/mess", lower toward 0.08 or set 0.

- [ ] **Step 5: Mirror + commit**

```bash
git add -- frontend/src/superbrain/components/canvas/HorizonGlow.tsx frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(gagos): faint horizon glow for restrained depth

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Intake organ + "speak to me" invitation (product-only)

**Files:**
- Modify: `frontend/src/workbench/BrainstemIntake.jsx`

In points mode the ring/core/conduit chrome is already hidden. Replace its absence with ONE subtle palette-tinted organ at the intake that pulses at rest (the living invitation), plus a faint "speak to me" cue that recedes the instant a turn starts. The existing prompt/intake text stays (it's already crisp — keep `outlineWidth`, no blur).

- [ ] **Step 1: Add a single intake organ for points mode**

Inside the intake `<group position={INTAKE_LOCAL} …>`, add a points-mode organ (sibling to the existing `{!POINTS_BEING && (<>…chrome…</>)}` block):

```jsx
{POINTS_BEING && (
  <mesh ref={coreRef} renderOrder={5}>
    <sphereGeometry args={[0.05, 20, 14]} />
    <meshBasicMaterial
      color="#7fe9ff"
      transparent
      opacity={0.5}
      blending={THREE.AdditiveBlending}
      depthWrite={false}
    />
  </mesh>
)}
```

(`coreRef` already exists and is driven in `useFrame` — the existing core animation, lines ~565–570, now animates this organ. It tints with `held` toward AMBER on approval, which is correct living behavior.)

- [ ] **Step 2: Add the resting "speak to me" invitation**

Compute an idle flag and render a faint cue under the organ. Near `intakeLabel` (~line 616):

```jsx
const idleInviting = !busy && !listening && !promptText && !replyText && !errorText;
```

Add this JSX inside the intake group, after the prompt billboard:

```jsx
{idleInviting ? (
  <Billboard position={[0, -0.52, 0.04]} follow>
    <Text
      color="#9fd6e6"
      fontSize={0.06}
      anchorX="center"
      anchorY="middle"
      outlineWidth={0.004}
      outlineColor="#03121a"
      letterSpacing={0.06}
      fillOpacity={0.7}
    >
      speak to me
    </Text>
  </Billboard>
) : null}
```

- [ ] **Step 3: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: PASS.

- [ ] **Step 4: Live fidelity check**

At `:5173/?being=points`: at rest, a soft organ pulses at the brainstem with a faint "speak to me"; the cue disappears the moment you start a turn and the organ brightens. The organ sits at the stem, not on the cord.

- [ ] **Step 5: Commit (product-only — do NOT mirror)**

```bash
git add -- frontend/src/workbench/BrainstemIntake.jsx
git commit -m "feat(gagos): diegetic intake organ + 'speak to me' invitation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Tests**

Run: `npm test`
Expected: PASS (≥ 286 — the prior 284 + the new tabStore/activeBrain cases).

- [ ] **Step 2: Typecheck + lint**

Run: `npm run typecheck && npm run lint`
Expected: PASS, no warnings introduced.

- [ ] **Step 3: Mirror audit**

Confirm every changed `superbrain/*` file matches its lab copy (`GAG demo/gag-orchestrator/src/...`) and that `workbench/BrainstemIntake.jsx` was NOT mirrored. Spot-check with a diff of one readout file.

- [ ] **Step 4: Operator full fidelity pass at `:5173/?ui=superbrain&being=points`**

Walk the spec §8 checklist live:
1. GAGOS + live model + supervised legible top-left through a full orbit, glowing, dims while speaking.
2. Ask the being something → reply unfurls on a vertebra slab, readable, never over brain/spine, line-reveals, retracts cleanly.
3. Input organ reads as part of the body; "speak to me" invites at rest and recedes on first word; prompt text crisp (no smear).
4. At rest: identity + invitation + restrained voyaging drift + vignette + faint horizon; the void still reads clean.
5. FPS holds at the P6 budget (kimi-webbridge rAF probe; expect ~60 / ≥50 worst).

- [ ] **Step 5: Update progress memory**

Append the GAGOS communication+home milestone to `C:\Users\kumar\.claude\projects\C--Users-kumar-ai-editor\memory\alive-being-build-progress.md` (what landed, the `showReplySurface`/`REPLY_FILEPATH` reuse, the camera-child readout pattern, the dials `window.__GAGOS`).

---

## Self-review (author check against the spec)

**Spec coverage:**
- §5A GAGOS/LLM/supervised readout → Tasks 4, 5. ✅ (camera-child, blooms, dims while speaking, live model via `route`.)
- §5B home decor: voyaging → Task 6; vignette → Task 7; horizon → Task 8; invitation → Task 9. ✅
- §5C intake organ + crisp prompt → Task 9 (reply blur offender removed in Task 3). ✅
- §5D reply slab from a vertebra → Tasks 1, 2, 3. ✅ (reuses content slab + `getContentSurfacePlacement`; floating billboard removed.)
- §6 file table → matches the File-structure table here. ✅
- §7 non-goals respected (no 2D DOM; no being/palette/perf changes; no mesh changes; no default-flip; single live reply, no history). ✅
- §8 testing → Task 10 mirrors the spec checklist. ✅

**Placeholder scan:** every code step shows full code; no TBD/TODO; commands have expected output. ✅

**Type consistency:** `showReplySurface(text, options)` / `REPLY_FILEPATH` used identically in Tasks 1→2→3; `formatActiveBrainLine`/`getActiveBrain`/`setActiveBrain`/`subscribeActiveBrain` consistent across Tasks 4→5; `window.__GAGOS` dial keys (`x/y/z`, `horizon`) consistent across Tasks 5/8; `coreRef` reused (already exists) in Task 9. ✅

**Risk note:** the only non-pure-logic risk is the content slab rendering prose acceptably (line-reveal + wrap). Mitigated: reply is clamped to 220 chars upstream, and the live gate (Task 3 Step 7) catches any wrap/overflow before commit; fallback if unacceptable = a dedicated `reply` tab kind (more invasive, not needed unless the operator rejects the look).
