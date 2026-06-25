/**
 * soundEngine — the organism's voice. Fully synthesized (no assets), and
 * SOVEREIGN: silent until the operator's own SOUND click (which is also the
 * user gesture WebAudio requires). Everything rides the same cognition bus
 * the visuals ride, so what you hear is what actually happened:
 *
 *   ambient    breath-paced sub-hum (always, while enabled)
 *   tick       knowledge-acquired — a real trail/result landed
 *   shadow     VERIFICATION RED — a verifier said no (the tick's dark twin)
 *   arpeggio   SKILL MASTERED — the rarest, most-earned sound
 *   whoosh     a directive leaves the command bar
 *   sus chord  approval-required (the unresolved hang IS the meaning)
 *   resolve    approval approved (the suspension resolves) / low thud reject
 *   ebb        TRAIL WEAKENED — the dark side of stigmergy, the tick inverted
 *   fifth      AI-OS LINK lost / re-established (the brain goes blind / sees)
 *   tritone    AUDIT CHAIN BROKEN — the tamper alarm; the only sustained dread
 *
 * Volume discipline: master 0.5 into a safety limiter, every element
 * whisper-quiet. The hum sits just above the noise floor — presence, not
 * soundtrack. Peaks are staggered and compressed so a burst of events
 * ripples instead of summing into a spike.
 */

import { subscribeCognition, type CognitionEvent } from './cognitionBus';

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let ambGain: GainNode | null = null;
let ambientStop: ((stopAt?: number) => void) | null = null;
let unsubscribe: (() => void) | null = null;
// Off->on toggling can construct a new context while the prior one is still
// closing; the browser caps concurrent contexts, so we serialize on this.
let closing: Promise<void> | null = null;
// Same-frame acquisition ticks are staggered so K reinforced trails in one
// poll become a short ripple instead of K phase-coherent oscillators summing.
let tickN = 0;
let lastTickAt = 0;

export function isSoundOn(): boolean {
  return ctx !== null;
}

function blip(freq: number, durS: number, peak: number, type: OscillatorType = 'sine', delayS = 0): void {
  // state guard, not just null: while the context is suspended (tab/OS audio
  // interruption) currentTime freezes, so events scheduled now would all
  // detonate in phase on resume. Drop them instead.
  if (!ctx || !master || ctx.state !== 'running') return;
  const t0 = ctx.currentTime + delayS;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  gain.gain.setValueAtTime(0, t0);
  gain.gain.linearRampToValueAtTime(peak, t0 + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + durS);
  osc.connect(gain).connect(master);
  osc.start(t0);
  osc.stop(t0 + durS + 0.05);
}

function whoosh(): void {
  if (!ctx || !master || ctx.state !== 'running') return;
  const t0 = ctx.currentTime;
  const seconds = 0.5;
  const buffer = ctx.createBuffer(1, ctx.sampleRate * seconds, ctx.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  const band = ctx.createBiquadFilter();
  band.type = 'bandpass';
  band.Q.value = 1.6;
  band.frequency.setValueAtTime(220, t0);
  band.frequency.exponentialRampToValueAtTime(1400, t0 + seconds * 0.8);
  const gain = ctx.createGain();
  gain.gain.setValueAtTime(0, t0);
  gain.gain.linearRampToValueAtTime(0.05, t0 + 0.06);
  gain.gain.exponentialRampToValueAtTime(0.0001, t0 + seconds);
  src.connect(band).connect(gain).connect(master);
  src.start(t0);
  src.stop(t0 + seconds);
}

function onCognition(event: CognitionEvent): void {
  const label = event.label ?? '';
  switch (event.type) {
    case 'directive':
      whoosh();
      return;
    case 'knowledge-acquired': {
      if (label.startsWith('SKILL MASTERED')) {
        // The earned sound: a slow rising major arpeggio.
        blip(440, 0.5, 0.05);
        blip(554.4, 0.5, 0.05, 'sine', 0.16);
        blip(659.3, 0.8, 0.06, 'sine', 0.32);
        return;
      }
      if (label === 'VERIFICATION RED') {
        // The tick's shadow: a falling, dissonant low semitone — clearly
        // "wrong", never the bright E6 acquisition ping. The ear hears the
        // truth (a failed verifier verdict), not a cheery acquisition.
        blip(207.65, 0.26, 0.034, 'triangle'); // G#3
        blip(196.0, 0.4, 0.03, 'triangle', 0.1); // -> G3, falling
        return;
      }
      // Generic acquisition tick (incl. VERIFICATION GREEN). Stagger
      // same-frame bursts so they ripple over ~70 ms instead of summing.
      const now = ctx ? ctx.currentTime : 0;
      if (now - lastTickAt > 0.07) {
        tickN = 0;
        lastTickAt = now;
      }
      blip(1318.5, 0.09, 0.028, 'sine', tickN * 0.045);
      tickN = Math.min(tickN + 1, 8);
      return;
    }
    case 'approval-required':
      // Suspended 2nd — deliberately unresolved while the mind waits.
      blip(220, 1.6, 0.035, 'triangle');
      blip(246.9, 1.6, 0.03, 'triangle');
      blip(329.6, 1.6, 0.025, 'triangle');
      return;
    case 'approval-resolved':
      if (label.startsWith('approved')) {
        blip(220, 0.9, 0.035, 'triangle');
        blip(277.2, 0.9, 0.03, 'triangle'); // the suspension resolves major
        blip(440, 1.1, 0.025, 'triangle', 0.1);
      } else {
        // Standing down: a low settle, lifted out of the ambient bed's mask
        // (E2, clear of the 110/165 Hz partials) and given its own space by
        // briefly ducking the hum. The operator's "no" must always read.
        if (ambGain && ctx) {
          const t = ctx.currentTime;
          ambGain.gain.setTargetAtTime(0.015, t, 0.05);
          ambGain.gain.setTargetAtTime(0.04, t + 0.5, 0.2);
        }
        blip(82.4, 0.6, 0.075, 'sine');
      }
      return;
    case 'agent-dispatch':
      if (label === 'TRAIL WEAKENED') {
        // The exact inverse of the rising acquisition tick, at half its
        // loudness: stigmergy's evaporation made audible.
        blip(659.3, 0.12, 0.02, 'sine');
        blip(587.3, 0.16, 0.018, 'sine', 0.08); // E5 -> D5, falling
      }
      return;
    case 'synthesis':
      if (label === 'AI-OS LINK LOST') {
        // Falling fifth — the brain goes blind, runs on imagination.
        blip(220, 0.4, 0.03);
        blip(164.8, 0.7, 0.03, 'sine', 0.2); // A3 -> E3
      } else if (label === 'AI-OS LINK ESTABLISHED') {
        // Its mirror — sight returns.
        blip(164.8, 0.3, 0.026);
        blip(220, 0.45, 0.026, 'sine', 0.12); // E3 -> A3
      } else if (label === 'AUDIT CHAIN BROKEN') {
        // The tamper alarm: a sustained tritone, the only other deliberately
        // uneasy long tone besides the approval sus chord. Silence on the
        // highest-stakes security event is not acceptable.
        blip(220, 1.2, 0.04, 'triangle');
        blip(311.1, 1.2, 0.038, 'triangle');
      }
      return;
    default:
      return;
  }
}

/** Start the voice — must be called from a user gesture (the SOUND click). */
export function startSound(): void {
  if (typeof window === 'undefined' || ctx) return;
  // A prior context may still be releasing; wait one tick and retry rather
  // than racing it and exhausting the browser's AudioContext slots.
  if (closing) {
    void closing.then(() => startSound());
    return;
  }
  const Ctor = window.AudioContext ?? (window as unknown as Record<string, unknown>).webkitAudioContext;
  if (!Ctor) return;
  ctx = new (Ctor as typeof AudioContext)();
  void ctx.resume();
  // Recover from OS-level interruptions (phone call, Bluetooth switch): the
  // context suspends and would never resume, leaving isSoundOn() lying.
  ctx.onstatechange = () => {
    if (ctx && ctx.state === 'suspended') void ctx.resume();
  };
  master = ctx.createGain();
  master.gain.value = 0.5;
  // Safety limiter: transparent at canon whisper levels, only acts on
  // pile-ups (e.g. a poll reinforcing many trails at once).
  const comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -18;
  comp.knee.value = 6;
  comp.ratio.value = 12;
  comp.attack.value = 0.002;
  comp.release.value = 0.25;
  master.connect(comp).connect(ctx.destination);

  // Ambient breath: two lows through a dark filter, swelling on the same
  // ~0.1 Hz pace the cortex breathes at. oscB rides 165.6 Hz so it actually
  // beats (~0.6 Hz shimmer) against the triangle's real 3rd harmonic (165 Hz);
  // a 55 Hz triangle has no energy at its own octave, so the old 110.4 Hz
  // had no partner and the documented beat never existed.
  const oscA = ctx.createOscillator();
  oscA.type = 'triangle';
  oscA.frequency.value = 55;
  const oscB = ctx.createOscillator();
  oscB.type = 'sine';
  oscB.frequency.value = 165.6; // beats against A's 3rd harmonic, not silence
  const low = ctx.createBiquadFilter();
  low.type = 'lowpass';
  low.frequency.value = 240;
  const amb = ctx.createGain();
  amb.gain.value = 0.04;
  ambGain = amb;
  const lfo = ctx.createOscillator();
  lfo.frequency.value = 0.1;
  const lfoDepth = ctx.createGain();
  lfoDepth.gain.value = 0.018;
  lfo.connect(lfoDepth).connect(amb.gain);
  oscA.connect(low);
  oscB.connect(low);
  low.connect(amb).connect(master);
  oscA.start();
  oscB.start();
  lfo.start();
  ambientStop = (stopAt?: number) => {
    const tt = stopAt ?? (ctx ? ctx.currentTime : 0);
    // Scheduled stops AFTER the master fade so the waveform is never
    // truncated mid-phase (the old zero-release stop() popped audibly).
    oscA.stop(tt + 0.25);
    oscB.stop(tt + 0.25);
    lfo.stop(tt + 0.25);
  };

  unsubscribe = subscribeCognition(onCognition);
}

/** Stop the voice and release the audio device entirely. */
export function stopSound(): void {
  unsubscribe?.();
  unsubscribe = null;
  const c = ctx;
  const m = master;
  // Flip isSoundOn() synchronously; the device release happens silently after.
  ctx = null;
  master = null;
  ambGain = null;
  if (!c) {
    ambientStop?.();
    ambientStop = null;
    return;
  }
  c.onstatechange = null;
  const t = c.currentTime;
  // Release the whole bus over ~200 ms, then stop oscillators, then close —
  // no hard cut at audible gain, and any in-flight blip/chord tail survives.
  m?.gain.setTargetAtTime(0, t, 0.04);
  ambientStop?.(t);
  ambientStop = null;
  closing = new Promise<void>((resolve) => {
    window.setTimeout(() => {
      void c.close().catch(() => undefined).finally(() => resolve());
    }, 300);
  }).finally(() => {
    closing = null;
  });
}

/** Test-only reset hook. Not part of the public API. */
export function __resetSoundEngineForTests(): void {
  unsubscribe?.();
  unsubscribe = null;
  ctx = null;
  master = null;
  ambGain = null;
  ambientStop = null;
  closing = null;
  tickN = 0;
  lastTickAt = 0;
}

/** Test-only context injection hook. Not part of the public API. */
export function __setAudioContextForTests(
  nextCtx: AudioContext | null,
  nextMaster: GainNode | null = null,
  nextAmb: GainNode | null = null,
): void {
  ctx = nextCtx;
  master = nextMaster;
  ambGain = nextAmb;
}
