// commandDockState (NeuralCommandDock — operator's hybrid): the chat input is kept
// usable but transformed into a control ORGAN connected to the being — "I type into
// a control organ and my words travel into its nervous system," not "a web chatbox
// over a 3D background." This pure contract decides the dock's live state from the
// input/voice/lifecycle; the chrome (membrane intensity, pulse, minimize) consumes
// it — it invents nothing. Geometry/luminance/motion only (sacred palette held).

export interface CommandDockStateInput {
  /** the draft has text. */
  hasText: boolean;
  /** the input is focused. */
  focused: boolean;
  /** voice capture is live. */
  listening: boolean;
  /** a turn is sending / the being is mid-reply. */
  sending: boolean;
  /** the being is orchestrating work (the dock should yield to the active work). */
  working: boolean;
  /** reduced-motion: suppress the travelling pulse/beads (luminance still varies). */
  reducedMotion: boolean;
}

export interface CommandDockState {
  /** 0..1 membrane glow/brightness — calm at rest, bright when engaged, dim when working. */
  intensity: number;
  /** the dock is engaged (typing / focused / listening). */
  active: boolean;
  /** command travel toward the brainstem: 'up' while engaged/sending, else 'none'. */
  pulse: 'none' | 'up';
  /** 0..1 command-bead flow rising into the stem (peaks while sending). */
  particleFlow: number;
  /** the dock recedes (subordinate) while the being works — never competes with it. */
  minimized: boolean;
}

const REST_INTENSITY = 0.4; // calm but present
const ENGAGED_INTENSITY = 0.85; // typing / focused / listening
const WORKING_INTENSITY = 0.24; // subordinate while the being works
const round3 = (v: number) => Math.round(v * 1000) / 1000;

export function deriveCommandDockState(i: CommandDockStateInput): CommandDockState {
  const engaged = i.focused || i.hasText || i.listening;
  // While the being works AND the operator isn't actively engaging the dock, it
  // yields — dim + minimized — so the active work owns attention.
  const subordinate = i.working && !engaged;

  let intensity: number;
  if (subordinate) intensity = WORKING_INTENSITY;
  else if (engaged || i.sending) intensity = ENGAGED_INTENSITY;
  else intensity = REST_INTENSITY;

  // Command travels UP into the stem while engaged or sending (reduced-motion: no travel).
  const wantsPulse = (engaged || i.sending) && !i.reducedMotion;
  const pulse: 'none' | 'up' = wantsPulse ? 'up' : 'none';

  // Beads rise strongest while sending, a gentle flow while typing.
  let particleFlow = 0;
  if (!i.reducedMotion) {
    if (i.sending) particleFlow = 1;
    else if (engaged) particleFlow = 0.45;
  }

  return {
    intensity: round3(intensity),
    active: engaged,
    pulse,
    particleFlow: round3(particleFlow),
    minimized: subordinate,
  };
}
