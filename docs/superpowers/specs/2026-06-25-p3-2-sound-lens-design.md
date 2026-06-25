# P3-2 Sound Lens — Design Spec

> Scope: the first sub-project of the 132-finding superbrain micro-detail renovation.
> Source: `.aios/state/RECOVERED_micro_detail_findings.md`, `sound` section.
> Work location: `GAG demo/gag-orchestrator/` lab.

## Goal

Lock the already-implemented sound-engine behavior with unit tests, and fix any gap the tests expose. The Fable `[C]` findings for the sound lens are already addressed in current `src/lib/soundEngine.ts`; this sub-project turns them from accidental correctness into verified, regression-protected behavior.

## Background

The recovered audit listed four Fable-confirmed sound issues:

1. `VERIFICATION RED` played the bright success tick.
2. `stopSound()` hard-cut the ambient hum and closed the context mid-flight (audible pop).
3. Same-frame trail polls stacked phase-coherent ticks into a piercing spike.
4. The reject thud was frequency-masked by the ambient hum.

Current `soundEngine.ts` already implements fixes for all four, plus several `[ ]` (unverified) improvements:

- Suspended-context guard in `blip()`/`whoosh()`.
- Close/reopen race serialization via `closing`.
- OS-level suspension auto-resume via `onstatechange`.
- Safety limiter on the master bus.
- Dark-event sounds for `TRAIL WEAKENED`, `AI-OS LINK LOST/ESTABLISHED`, and `AUDIT CHAIN BROKEN`.
- Corrected ambient detune beat (165.6 Hz sine against the 55 Hz triangle's 3rd harmonic).

The missing piece is **test coverage**.

## Architecture

`soundEngine.ts` remains a side-effect module that owns one `AudioContext` and one cognition-bus subscription. It is not refactored into a class; the public API stays:

- `startSound()` — idempotent, user-gesture triggered.
- `stopSound()` — releases the audio device with a fade.
- `isSoundOn()` — reflects the active state.

For testability only, the module exposes two internal helpers:

- `__setAudioContextForTests(ctx: AudioContext)` — replaces the module's `ctx`/`master`/`ambGain` references with a stub.
- `__resetSoundEngineForTests()` — nulls all module state and unsubscribes.

These helpers are stripped from production bundles by convention (the lab already uses this pattern in `replyVoiceBus.ts`).

## Behaviors under test

### 1. Context construction (`startSound`)

- Creates `master` gain set to `0.5`.
- Creates a `DynamicsCompressorNode` with the documented thresholds (`threshold -18`, `knee 6`, `ratio 12`, `attack 0.002`, `release 0.25`).
- Connects `master → compressor → destination`.
- Creates ambient oscillators: 55 Hz triangle + 165.6 Hz sine.
- Creates an LFO at 0.1 Hz modulating ambient gain.
- Subscribes to the cognition bus.

### 2. Cognition event mapping

| Event type | Label | Expected sound |
|------------|-------|----------------|
| `directive` | any | `whoosh()` |
| `knowledge-acquired` | `SKILL MASTERED` | major arpeggio 440/554.4/659.3 Hz |
| `knowledge-acquired` | `VERIFICATION RED` | falling D#5→D5 triangle (622.3 Hz then 587.3 Hz) |
| `knowledge-acquired` | any other | staggered E6 sine ticks (1318.5 Hz), delay = `tickN * 0.045` |
| `approval-required` | any | suspended 2nd chord 220/246.9/329.6 Hz |
| `approval-resolved` | starts with `approved` | resolving major chord 220/277.2/440 Hz |
| `approval-resolved` | any other | ducks ambient gain + E2 sine thud (82.4 Hz) |
| `agent-dispatch` | `TRAIL WEAKENED` | falling E5→D5 659.3/587.3 Hz |
| `synthesis` | `AI-OS LINK LOST` | falling fifth 220→164.8 Hz |
| `synthesis` | `AI-OS LINK ESTABLISHED` | rising fifth 164.8→220 Hz |
| `synthesis` | `AUDIT CHAIN BROKEN` | sustained tritone 220/311.1 Hz |

### 3. Tick staggering

Three generic `knowledge-acquired` events fired in the same JS tick schedule three E6 blips at `currentTime + 0`, `+0.045`, `+0.090`. `tickN` saturates at 8.

### 4. Stop/release discipline (`stopSound`)

- Unsubscribes from the cognition bus.
- Nulls `ctx`/`master` synchronously so `isSoundOn()` returns false immediately.
- Fades `master.gain` to 0 with a 40 ms time constant.
- Schedules ambient oscillator stops at `currentTime + 0.25`.
- Closes the context after ~300 ms.
- Handles repeated calls without error.

### 5. State guards

- `blip()` and `whoosh()` return early if `ctx` is null or `ctx.state !== 'running'`.
- `startSound()` is a no-op if `ctx` already exists.
- `startSound()` waits for an in-flight `closing` promise before retrying.

## Test strategy

- New file: `GAG demo/gag-orchestrator/src/lib/soundEngine.test.ts`.
- Runner: vitest (existing lab test runner).
- Mock: a minimal `AudioContext` stub that records `create*()` calls, `currentTime`, `state`, `destination`, and exposes parameter methods (`setValueAtTime`, `linearRampToValueAtTime`, `exponentialRampToValueAtTime`, `setTargetAtTime`).
- Mock `window.setTimeout` and `window.AudioContext` for Node safety.
- Each test calls `__resetSoundEngineForTests()` in `beforeEach`.

## Error handling / edge cases

- Calling `stopSound()` when sound was never started must not throw.
- Calling `startSound()` when `typeof window === 'undefined'` must not throw.
- Rapid `startSound()`/`stopSound()` cycles must not exhaust context slots.

## Visual / canon impact

This lens changes no pixels. Existing lab goldens must remain byte-identical. The only product-side artifact after `npm run port` is the same `soundEngine.ts` file; palette/texture canon is untouched.

## Definition of done

- [ ] `src/lib/soundEngine.test.ts` exists and all tests pass (`npm test` in the lab).
- [ ] No regressions in existing lab tests.
- [ ] Goldens unchanged.
- [ ] Lab commit with a clear message referencing this spec.
- [ ] `npm run port` succeeds and product tests pass.
- [ ] Operator browser sign-off (sound on/off, tick, reject, approval sus chord).

## Next step

Invoke the `writing-plans` skill to produce a step-by-step implementation plan for this spec.
