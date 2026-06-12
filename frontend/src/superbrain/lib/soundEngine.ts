/**
 * soundEngine — the organism's voice. Fully synthesized (no assets), and
 * SOVEREIGN: silent until the operator's own SOUND click (which is also the
 * user gesture WebAudio requires). Everything rides the same cognition bus
 * the visuals ride, so what you hear is what actually happened:
 *
 *   ambient    breath-paced sub-hum (always, while enabled)
 *   tick       knowledge-acquired — a real trail/result landed
 *   arpeggio   SKILL MASTERED — the rarest, most-earned sound
 *   whoosh     a directive leaves the command bar
 *   sus chord  approval-required (the unresolved hang IS the meaning)
 *   resolve    approval approved (the suspension resolves) / low thud reject
 *
 * Volume discipline: master 0.5, every element whisper-quiet. The hum sits
 * just above the noise floor — presence, not soundtrack.
 */

import { subscribeCognition, type CognitionEvent } from './cognitionBus';

let ctx: AudioContext | null = null;
let master: GainNode | null = null;
let ambientStop: (() => void) | null = null;
let unsubscribe: (() => void) | null = null;

export function isSoundOn(): boolean {
  return ctx !== null;
}

function blip(freq: number, durS: number, peak: number, type: OscillatorType = 'sine', delayS = 0): void {
  if (!ctx || !master) return;
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
  if (!ctx || !master) return;
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
  switch (event.type) {
    case 'directive':
      whoosh();
      return;
    case 'knowledge-acquired': {
      if ((event.label ?? '').startsWith('SKILL MASTERED')) {
        // The earned sound: a slow rising major arpeggio.
        blip(440, 0.5, 0.05);
        blip(554.4, 0.5, 0.05, 'sine', 0.16);
        blip(659.3, 0.8, 0.06, 'sine', 0.32);
        return;
      }
      blip(1318.5, 0.09, 0.028);
      return;
    }
    case 'approval-required':
      // Suspended 2nd — deliberately unresolved while the mind waits.
      blip(220, 1.6, 0.035, 'triangle');
      blip(246.9, 1.6, 0.03, 'triangle');
      blip(329.6, 1.6, 0.025, 'triangle');
      return;
    case 'approval-resolved':
      if ((event.label ?? '').startsWith('approved')) {
        blip(220, 0.9, 0.035, 'triangle');
        blip(277.2, 0.9, 0.03, 'triangle'); // the suspension resolves major
        blip(440, 1.1, 0.025, 'triangle', 0.1);
      } else {
        blip(98, 0.5, 0.05, 'sine'); // standing down: a low settle
      }
      return;
    default:
      return;
  }
}

/** Start the voice — must be called from a user gesture (the SOUND click). */
export function startSound(): void {
  if (typeof window === 'undefined' || ctx) return;
  const Ctor = window.AudioContext ?? (window as unknown as Record<string, unknown>).webkitAudioContext;
  if (!Ctor) return;
  ctx = new (Ctor as typeof AudioContext)();
  void ctx.resume();
  master = ctx.createGain();
  master.gain.value = 0.5;
  master.connect(ctx.destination);

  // Ambient breath: two detuned lows through a dark filter, swelling on the
  // same ~0.1 Hz pace the cortex breathes at.
  const oscA = ctx.createOscillator();
  oscA.type = 'triangle';
  oscA.frequency.value = 55;
  const oscB = ctx.createOscillator();
  oscB.type = 'sine';
  oscB.frequency.value = 110.4; // slight detune against A's octave
  const low = ctx.createBiquadFilter();
  low.type = 'lowpass';
  low.frequency.value = 240;
  const amb = ctx.createGain();
  amb.gain.value = 0.04;
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
  ambientStop = () => {
    oscA.stop();
    oscB.stop();
    lfo.stop();
  };

  unsubscribe = subscribeCognition(onCognition);
}

/** Stop the voice and release the audio device entirely. */
export function stopSound(): void {
  unsubscribe?.();
  unsubscribe = null;
  ambientStop?.();
  ambientStop = null;
  if (ctx) {
    void ctx.close();
    ctx = null;
    master = null;
  }
}
