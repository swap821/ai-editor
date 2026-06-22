# Voice Into the Body — SP1: Reply as In-Scene Body-Speech — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the being's chat reply as luminous 3D text emanating from its own anatomy (cortex/upper-stem) instead of a 2D DOM thread bubble — "the being speaks back as a being."

**Architecture:** A pure contract `deriveBodySpeech` decides what text shows + its glow/fade from a reply-voice signal; a module store `replyVoiceBus` accumulates the reply from the cognition bus the chat already publishes; a renderer `BodySpeech` (drei `<Text>`) consumes the derived state in the points scene. The DOM thread stops duplicating GAGOS's reply (keeps the user's echo). Sacred palette untouched; luminance/anatomy only.

**Tech Stack:** React Three Fiber, drei `<Text>`, three.js, Vitest. Spec: `docs/superpowers/specs/2026-06-22-voice-into-body-design.md`.

---

## File Structure

- Create `frontend/src/superbrain/lib/bodySpeech.ts` — pure `deriveBodySpeech` contract.
- Create `frontend/src/superbrain/lib/bodySpeech.test.ts` — focused tests.
- Create `frontend/src/superbrain/lib/replyVoiceBus.ts` — singleton store: subscribes to cognition `voice-speaking`, exposes `getReplyVoice()` / `subscribeReplyVoice()`; dev hook `window.__getBodySpeech`.
- Create `frontend/src/superbrain/lib/replyVoiceBus.test.ts` — focused tests.
- Create `frontend/src/superbrain/components/canvas/BodySpeech.tsx` — renderer.
- Modify `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` — mount `BodySpeech` (points mode).
- Modify `frontend/src/workbench/GagosChrome.jsx` — stop pushing the GAGOS chat reply into the DOM thread (keep events + user echo).

---

### Task 1: `deriveBodySpeech` pure contract

**Files:**
- Create: `frontend/src/superbrain/lib/bodySpeech.ts`
- Test: `frontend/src/superbrain/lib/bodySpeech.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { deriveBodySpeech, BODY_SPEECH_HOLD_MS, BODY_SPEECH_FADE_MS } from './bodySpeech';

describe('deriveBodySpeech', () => {
  it('idle: nothing visible', () => {
    const o = deriveBodySpeech({ text: '', phase: 'idle', sinceMs: 0, reducedMotion: false });
    expect(o.active).toBe(false);
    expect(o.visibleText).toBe('');
    expect(o.glow).toBe(0);
  });
  it('streaming: full text, full glow, no fade', () => {
    const o = deriveBodySpeech({ text: 'hello there', phase: 'streaming', sinceMs: 200, reducedMotion: false });
    expect(o.active).toBe(true);
    expect(o.visibleText).toBe('hello there');
    expect(o.glow).toBeGreaterThan(0.6);
    expect(o.fade).toBe(0);
  });
  it('complete within hold: still visible, fade 0', () => {
    const o = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS - 1, reducedMotion: false });
    expect(o.active).toBe(true);
    expect(o.fade).toBe(0);
  });
  it('complete after hold: fades over the fade window', () => {
    const mid = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS + BODY_SPEECH_FADE_MS / 2, reducedMotion: false });
    expect(mid.fade).toBeGreaterThan(0.3);
    expect(mid.fade).toBeLessThan(0.7);
    const gone = deriveBodySpeech({ text: 'done', phase: 'complete', sinceMs: BODY_SPEECH_HOLD_MS + BODY_SPEECH_FADE_MS + 10, reducedMotion: false });
    expect(gone.active).toBe(false);
  });
  it('caps very long replies to a readable tail', () => {
    const long = 'x'.repeat(2000);
    const o = deriveBodySpeech({ text: long, phase: 'streaming', sinceMs: 10, reducedMotion: false });
    expect(o.visibleText.length).toBeLessThanOrEqual(360);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/superbrain/lib/bodySpeech.test.ts`
Expected: FAIL ("deriveBodySpeech is not a function" / module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/superbrain/lib/bodySpeech.ts
// Pure contract: turn the reply-voice signal into what the BodySpeech renderer draws.
// No THREE, no DOM — testable in isolation. Luminance/text only (sacred palette held).
export type BodySpeechPhase = 'idle' | 'streaming' | 'complete' | 'error';

export interface BodySpeechInput {
  text: string;        // accumulated reply text so far
  phase: BodySpeechPhase;
  sinceMs: number;     // ms since the current phase began
  reducedMotion: boolean;
}
export interface BodySpeechOutput {
  visibleText: string;
  glow: number;   // 0..1 luminance weight
  fade: number;   // 0..1 (1 = fully faded out)
  active: boolean;
}

/** How long a completed reply lingers before it begins to fade. */
export const BODY_SPEECH_HOLD_MS = 2600;
/** How long the fade-out takes once it begins. */
export const BODY_SPEECH_FADE_MS = 1400;
/** Max characters shown (readable tail of long replies). */
export const BODY_SPEECH_MAX_CHARS = 360;

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

export function deriveBodySpeech(input: BodySpeechInput): BodySpeechOutput {
  const { text, phase, sinceMs } = input;
  const trimmed = text.length > BODY_SPEECH_MAX_CHARS ? text.slice(text.length - BODY_SPEECH_MAX_CHARS) : text;

  if (phase === 'idle' || (!trimmed && phase !== 'error')) {
    return { visibleText: '', glow: 0, fade: 0, active: false };
  }
  if (phase === 'streaming') {
    return { visibleText: trimmed, glow: 1, fade: 0, active: true };
  }
  // complete / error: hold, then fade out
  const overHold = sinceMs - BODY_SPEECH_HOLD_MS;
  const fade = overHold <= 0 ? 0 : clamp01(overHold / BODY_SPEECH_FADE_MS);
  const active = fade < 1;
  const glow = active ? (1 - fade) * (phase === 'error' ? 0.7 : 0.85) : 0;
  return { visibleText: active ? trimmed : '', glow, fade, active };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/superbrain/lib/bodySpeech.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/superbrain/lib/bodySpeech.ts frontend/src/superbrain/lib/bodySpeech.test.ts
git commit -m "feat(being): deriveBodySpeech pure contract (SP1 reply body-speech)"
```

---

### Task 2: `replyVoiceBus` store (cognition-bus reply accumulator + proof hook)

**Files:**
- Create: `frontend/src/superbrain/lib/replyVoiceBus.ts`
- Test: `frontend/src/superbrain/lib/replyVoiceBus.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect, beforeEach } from 'vitest';
import { getReplyVoice, __ingestVoiceForTests, __resetReplyVoiceForTests } from './replyVoiceBus';

describe('replyVoiceBus', () => {
  beforeEach(() => __resetReplyVoiceForTests());
  it('starts idle', () => {
    expect(getReplyVoice().phase).toBe('idle');
    expect(getReplyVoice().text).toBe('');
  });
  it('question resets, reply accumulates (latest chunk is full text), complete marks complete', () => {
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'question', text: 'hi' } });
    expect(getReplyVoice().phase).toBe('idle');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hel' } });
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply', reply: 'Hello' } });
    expect(getReplyVoice().phase).toBe('streaming');
    expect(getReplyVoice().text).toBe('Hello');
    __ingestVoiceForTests({ type: 'voice-speaking', source: 'gagos', data: { phase: 'reply-complete' } });
    expect(getReplyVoice().phase).toBe('complete');
    expect(getReplyVoice().text).toBe('Hello');
  });
  it('ignores non-voice-speaking events', () => {
    __ingestVoiceForTests({ type: 'directive', source: 'hud' });
    expect(getReplyVoice().phase).toBe('idle');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/superbrain/lib/replyVoiceBus.test.ts`
Expected: FAIL (module not found).

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/superbrain/lib/replyVoiceBus.ts
// Singleton store: the being's current spoken reply, read off the SAME voice-speaking
// cognition events the chat already publishes (GagosChrome). SSR-safe; mirrors the
// conversationPhaseBus pattern. The point scene polls getReplyVoice() each frame.
import { subscribeCognition } from './cognitionBus';
import type { BodySpeechPhase } from './bodySpeech';

interface ReplyVoiceState { phase: BodySpeechPhase; text: string; since: number; }
let state: ReplyVoiceState = { phase: 'idle', text: '', since: 0 };
const listeners = new Set<() => void>();

function nowMs(): number {
  return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
}
function set(next: ReplyVoiceState): void {
  state = next;
  for (const l of listeners) { try { l(); } catch { /* one bad listener never breaks the rest */ } }
}
function ingest(event: { type: string; source?: string; data?: { phase?: string; reply?: string } }): void {
  if (event.type !== 'voice-speaking') return;
  const p = event.data?.phase ?? '';
  if (p === 'question') { set({ phase: 'idle', text: '', since: nowMs() }); return; }
  if (p === 'reply') { set({ phase: 'streaming', text: String(event.data?.reply ?? ''), since: nowMs() }); return; }
  if (p === 'reply-complete') { set({ phase: 'complete', text: state.text, since: nowMs() }); return; }
  if (p === 'error') { set({ phase: 'error', text: state.text, since: nowMs() }); }
}

export function getReplyVoice(): ReplyVoiceState { return state; }
export function subscribeReplyVoice(l: () => void): () => void { listeners.add(l); return () => { listeners.delete(l); }; }

// Wire to the cognition bus once (browser only).
if (typeof window !== 'undefined') {
  subscribeCognition((e) => ingest(e as Parameters<typeof ingest>[0]));
  (window as unknown as { __getBodySpeech?: () => ReplyVoiceState }).__getBodySpeech = () => state;
}

export function __ingestVoiceForTests(e: Parameters<typeof ingest>[0]): void { ingest(e); }
export function __resetReplyVoiceForTests(): void { state = { phase: 'idle', text: '', since: 0 }; listeners.clear(); }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/superbrain/lib/replyVoiceBus.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/superbrain/lib/replyVoiceBus.ts frontend/src/superbrain/lib/replyVoiceBus.test.ts
git commit -m "feat(being): replyVoiceBus store + __getBodySpeech hook (SP1)"
```

---

### Task 3: `BodySpeech` renderer

**Files:**
- Create: `frontend/src/superbrain/components/canvas/BodySpeech.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client';
// BodySpeech (poster phase 3): the being's reply as luminous body-speech — drei <Text>
// emanating at the upper stem / cortex base, camera-billboarded, streaming + settling
// per deriveBodySpeech. Reads the reply off replyVoiceBus; renderer invents nothing.
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Text } from '@react-three/drei';
import * as THREE from 'three';
import { getReplyVoice } from '@/lib/replyVoiceBus';
import { deriveBodySpeech } from '@/lib/bodySpeech';

const REDUCED = typeof window !== 'undefined' && !!window.matchMedia
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export default function BodySpeech({ color = '#7bf5fb' }: { color?: string }) {
  const ref = useRef<THREE.Group>(null);
  const textRef = useRef<{ fillOpacity?: number; outlineOpacity?: number } | null>(null);
  const col = useMemo(() => new THREE.Color(color), [color]);
  const textState = useRef({ text: '', visible: false });

  useFrame(() => {
    const v = getReplyVoice();
    const o = deriveBodySpeech({ text: v.text, phase: v.phase, sinceMs: (performance.now() - v.since), reducedMotion: REDUCED });
    const g = ref.current;
    if (!g) return;
    g.visible = o.active;
    textState.current.text = o.visibleText;
    textState.current.visible = o.active;
    const op = (1 - o.fade) * (0.45 + 0.55 * o.glow);
    const t = textRef.current;
    if (t) { t.fillOpacity = op; t.outlineOpacity = op * 0.6; }
  });

  return (
    <group ref={ref} position={[0, 0.18, 0.2]} visible={false}>
      <Text
        ref={textRef as never}
        position={[0, 0, 0]}
        color={col}
        fontSize={0.09}
        maxWidth={2.4}
        lineHeight={1.25}
        anchorX="center"
        anchorY="top"
        textAlign="center"
        outlineWidth={0.006}
        outlineColor="#02040a"
        material-toneMapped={false}
        renderOrder={12}
      >
        {/* drei <Text> reads children imperatively; BodySpeech sets text via a ticking child */}
        <BodySpeechText state={textState} />
      </Text>
    </group>
  );
}

// Small ticking child that pushes the current text into the parent <Text>. Keeping the
// text update out of React state avoids a re-render per chunk.
function BodySpeechText({ state }: { state: React.MutableRefObject<{ text: string; visible: boolean }> }) {
  const last = useRef('');
  useFrame(() => {
    const el = state.current;
    // no-op placeholder; text is set on the Text instance below via troika in Step note
  });
  return null;
}
```

> NOTE (implementation detail to resolve during build): drei `<Text>` takes its string as
> children. Since the reply streams, set the text imperatively on the troika text instance
> (`textRef.current.text = visibleText; textRef.current.sync()`) inside the `useFrame`
> rather than via the `BodySpeechText` child — simpler + no per-chunk React re-render.
> Replace the children/`BodySpeechText` shim with the imperative `text`/`sync()` approach
> when wiring (troika exposes `.text` + `.sync()` on the ref). Verify the ref type.

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npm run typecheck`
Expected: PASS (no type errors). Fix the `textRef` typing to the troika text instance.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/superbrain/components/canvas/BodySpeech.tsx
git commit -m "feat(being): BodySpeech renderer — luminous reply text (SP1)"
```

---

### Task 4: Mount `BodySpeech` in the points scene

**Files:**
- Modify: `frontend/src/superbrain/components/canvas/SuperbrainScene.tsx` (near the other `BEING_MODE === 'points'` mounts, e.g. by `<PostFX />`)

- [ ] **Step 1: Add the import + mount**

```tsx
// import near the other canvas imports:
import BodySpeech from './BodySpeech';

// in the returned scene tree, points mode only (mirror the NervousSystem gate):
{BEING_MODE === 'points' && <BodySpeech />}
```

- [ ] **Step 2: Typecheck + build**

Run: `cd frontend && npm run typecheck && npm run build`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/superbrain/components/canvas/SuperbrainScene.tsx
git commit -m "feat(being): mount BodySpeech in the points scene (SP1)"
```

---

### Task 5: DOM thread → secondary (stop duplicating GAGOS's chat reply)

**Files:**
- Modify: `frontend/src/workbench/GagosChrome.jsx` (the CHAT branch, ~`360-373`)

- [ ] **Step 1: Stop rendering the GAGOS reply bubble for chat turns**

In the CHAT branch, keep publishing the `voice-speaking` reply events (BodySpeech depends on them) and keep the user's pushed message, but do NOT create/update the `gagos` reply bubble in the DOM thread. Concretely: do not `pushMessage('gagos', '')` for the chat path and drop the `updateMessage(gagosId, …)` calls; keep the `publishCognition(... phase:'reply' / 'reply-complete' ...)` calls intact. (Work-intent path that materializes a tab is unchanged.)

- [ ] **Step 2: Manual check**

The chat reply must NOT appear as a DOM bubble; the cognition events must still fire (BodySpeech shows the reply). The user's typed message still appears.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/workbench/GagosChrome.jsx
git commit -m "feat(being): DOM thread secondary — reply lives in the body, not a bubble (SP1)"
```

---

### Task 6: Gates + live verification (proof)

- [ ] **Step 1: Full gates**

Run: `cd frontend && npm run typecheck && npm test && npm run build`
Expected: typecheck clean; vitest ≥ 217 passing (209 + new); build green.

- [ ] **Step 2: Live proof on :5173 (kimi-webbridge)**

Navigate fresh; send a plain chat message ("Tell me a short two-sentence story."). Capture during streaming + at settle. Verify: the reply appears as luminous text emanating from the being (not a DOM bubble); cortex brightens + spine-rise still play; text settles then fades; `window.__getBodySpeech()` reflects phase/text. Save frames under `.aios/tmp/`.

- [ ] **Step 3: Commit any tuning + open PR**

```bash
git push -u origin feat/voice-into-body
gh pr create --base master --head feat/voice-into-body --title "feat(being): reply as in-scene body-speech (voice-into-body SP1)" --body "..."
```

---

## Self-Review

- **Spec coverage:** SP1 (reply → in-scene luminous body-speech; DOM thread secondary; proof hook; reduced-motion; sacred palette) — all covered by Tasks 1-6. SP2/SP3 are separate plans (out of scope here, per the spec's decomposition).
- **Placeholder scan:** one explicit, bounded implementation NOTE in Task 3 (drei `<Text>` imperative `.text`/`.sync()`) — resolved during build, not a vague TODO.
- **Type consistency:** `BodySpeechPhase` (idle|streaming|complete|error) shared by `bodySpeech.ts` + `replyVoiceBus.ts`; `getReplyVoice()` returns `{phase,text,since}`; `deriveBodySpeech({text,phase,sinceMs,reducedMotion})` — consistent across tasks.
