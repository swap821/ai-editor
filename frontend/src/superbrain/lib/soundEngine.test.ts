import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  isSoundOn,
  startSound,
  stopSound,
  __resetSoundEngineForTests,
  __setAudioContextForTests,
} from './soundEngine';
import * as cognitionBus from './cognitionBus';

/** Callable mock shape that accepts any args and exposes .mock.calls/.mockResolvedValue. */
type MockFn = ((...args: any[]) => any) & {
  mock: { calls: any[][] };
  mockResolvedValue: (value: unknown) => MockFn;
};

/** Cast vi.fn(...) to a callable MockFn so product typecheck accepts call sites. */
function mockFn<TArgs extends any[] = any[], TReturn = unknown>(
  impl?: (...args: TArgs) => TReturn,
): MockFn {
  return vi.fn(impl) as unknown as MockFn;
}

export interface MockAudioContext {
  state: AudioContextState;
  currentTime: number;
  sampleRate: number;
  destination: MockAudioNode;
  scheduled: ScheduledEvent[];
  nodes: MockAudioNode[];
  resume: MockFn;
  close: MockFn;
  createOscillator: () => MockAudioNode;
  createGain: () => MockAudioNode;
  createDynamicsCompressor: () => MockAudioNode;
  createBiquadFilter: () => MockAudioNode;
  createBuffer: (channels: number, length: number, sampleRate: number) => AudioBuffer;
  createBufferSource: () => MockAudioNode;
}

interface ScheduledEvent {
  node: MockAudioNode;
  param: string;
  method: string;
  args: unknown[];
}

interface MockAudioNode {
  type: string;
  frequency?: MockAudioParam;
  gain?: MockAudioParam;
  Q?: MockAudioParam;
  threshold?: MockAudioParam;
  knee?: MockAudioParam;
  ratio?: MockAudioParam;
  attack?: MockAudioParam;
  release?: MockAudioParam;
  buffer: AudioBuffer | null;
  onstatechange: (() => void) | null;
  connect: MockFn;
  disconnect: MockFn;
  start: MockFn;
  stop: MockFn;
}

interface MockAudioParam {
  value: number;
  setValueAtTime: MockFn;
  linearRampToValueAtTime: MockFn;
  exponentialRampToValueAtTime: MockFn;
  setTargetAtTime: MockFn;
}

function createMockParam(node: MockAudioNode, scheduled: ScheduledEvent[]): MockAudioParam {
  const param: MockAudioParam = {
    value: 0,
    setValueAtTime: mockFn((value, time) => {
      param.value = value;
      scheduled.push({ node, param: 'value', method: 'setValueAtTime', args: [value, time] });
    }),
    linearRampToValueAtTime: mockFn((value, time) => scheduled.push({ node, param: 'value', method: 'linearRampToValueAtTime', args: [value, time] })),
    exponentialRampToValueAtTime: mockFn((value, time) => scheduled.push({ node, param: 'value', method: 'exponentialRampToValueAtTime', args: [value, time] })),
    setTargetAtTime: mockFn((value, time, timeConstant) => scheduled.push({ node, param: 'value', method: 'setTargetAtTime', args: [value, time, timeConstant] })),
  };
  return param;
}

export function createMockAudioContext(): MockAudioContext {
  const scheduled: ScheduledEvent[] = [];
  const nodes: MockAudioNode[] = [];

  function node(type: string): MockAudioNode {
    const n: MockAudioNode = {
      type,
      buffer: null,
      onstatechange: null,
      connect: mockFn((dest) => dest),
      disconnect: mockFn(),
      start: mockFn(),
      stop: mockFn(),
    };
    if (type === 'oscillator' || type === 'biquad') {
      n.frequency = createMockParam(n, scheduled);
    }
    if (type === 'gain' || type === 'compressor') {
      n.gain = createMockParam(n, scheduled);
    }
    if (type === 'biquad') {
      n.Q = createMockParam(n, scheduled);
    }
    if (type === 'compressor') {
      n.threshold = createMockParam(n, scheduled);
      n.knee = createMockParam(n, scheduled);
      n.ratio = createMockParam(n, scheduled);
      n.attack = createMockParam(n, scheduled);
      n.release = createMockParam(n, scheduled);
    }
    nodes.push(n);
    return n;
  }

  const destination = node('destination');

  return {
    state: 'running',
    currentTime: 1.0,
    sampleRate: 48000,
    destination,
    scheduled,
    nodes,
    resume: mockFn(),
    close: mockFn().mockResolvedValue(undefined),
    createOscillator: () => node('oscillator'),
    createGain: () => node('gain'),
    createDynamicsCompressor: () => node('compressor'),
    createBiquadFilter: () => node('biquad'),
    createBuffer: () => ({ getChannelData: () => new Float32Array(100) } as unknown as AudioBuffer),
    createBufferSource: () => node('bufferSource'),
  };
}

const capturedCallbacks: Array<(event: cognitionBus.CognitionEvent) => void> = [];

vi.spyOn(cognitionBus, 'subscribeCognition').mockImplementation((cb) => {
  capturedCallbacks.push(cb);
  return () => {
    const i = capturedCallbacks.indexOf(cb);
    if (i >= 0) capturedCallbacks.splice(i, 1);
  };
});

function emitCognition(event: cognitionBus.CognitionEvent): void {
  capturedCallbacks.forEach((cb) => cb(event));
}

function stubAudioContext(mock: MockAudioContext): void {
  vi.stubGlobal('AudioContext', class {
    constructor() {
      return mock as unknown as AudioContext;
    }
  } as unknown as typeof AudioContext);
}

describe('soundEngine test hooks', () => {
  beforeEach(() => __resetSoundEngineForTests());

  it('exposes reset and set helpers', () => {
    expect(typeof __resetSoundEngineForTests).toBe('function');
    expect(typeof __setAudioContextForTests).toBe('function');
    expect(isSoundOn()).toBe(false);
  });
});

describe('createMockAudioContext', () => {
  it('records created nodes and scheduled events', () => {
    const mock = createMockAudioContext();
    const osc = mock.createOscillator();
    osc.frequency!.setValueAtTime(440, 0);
    expect(mock.nodes).toContain(osc);
    expect(mock.scheduled.length).toBe(1);
  });
});

describe('startSound', () => {
  beforeEach(() => {
    __resetSoundEngineForTests();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds the canon audio graph', () => {
    const mock = createMockAudioContext();
    vi.stubGlobal('AudioContext', class {
      constructor() {
        return mock as unknown as AudioContext;
      }
    } as unknown as typeof AudioContext);

    startSound();

    // master gain at 0.5
    const masterNode = mock.nodes.find((n) => n.type === 'gain' && n.gain?.value === 0.5);
    expect(masterNode).toBeDefined();

    // compressor thresholds
    const comp = mock.nodes.find((n) => n.type === 'compressor');
    expect(comp).toBeDefined();
    expect(comp?.threshold?.value).toBe(-18);

    // ambient oscillators
    const oscs = mock.nodes.filter((n) => n.frequency !== undefined);
    expect(oscs.length).toBeGreaterThanOrEqual(3);

    // ambient triangle at 55 Hz and sine at 165.6 Hz
    const triangle = oscs.find((n) => n.frequency?.value === 55);
    const sine = oscs.find((n) => n.frequency?.value === 165.6);
    expect(triangle).toBeDefined();
    expect(sine).toBeDefined();

    // LFO at 0.1 Hz
    const lfo = oscs.find((n) => n.frequency?.value === 0.1);
    expect(lfo).toBeDefined();

    expect(isSoundOn()).toBe(true);
  });
});

function oscillatorNodes(mock: MockAudioContext): MockAudioNode[] {
  return mock.nodes.filter((n) => n.frequency !== undefined && n.type !== 'biquad');
}

function lastOscillatorFrequencies(mock: MockAudioContext): number[] {
  return oscillatorNodes(mock).map((n) => n.frequency?.value ?? 0);
}

describe('onCognition event mapping', () => {
  beforeEach(() => {
    __resetSoundEngineForTests();
    capturedCallbacks.length = 0;
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function boot(mock: MockAudioContext): void {
    stubAudioContext(mock);
    startSound();
  }

  it('VERIFICATION RED plays a falling semitone, not the success E6 tick', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'knowledge-acquired', label: 'VERIFICATION RED', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(207.65);
    expect(freqs).toContain(196);
    expect(freqs).not.toContain(1318.5);
  });

  it('SKILL MASTERED plays a major arpeggio', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'knowledge-acquired', label: 'SKILL MASTERED', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(440);
    expect(freqs).toContain(554.4);
    expect(freqs).toContain(659.3);
  });

  it('TRAIL WEAKENED plays a falling E5→D5', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'agent-dispatch', label: 'TRAIL WEAKENED', intensity: 0.4 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(659.3);
    expect(freqs).toContain(587.3);
  });

  it('AI-OS LINK LOST plays a falling fifth A3→E3', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'synthesis', label: 'AI-OS LINK LOST', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(220);
    expect(freqs).toContain(164.8);
  });

  it('AI-OS LINK ESTABLISHED plays a rising fifth E3→A3', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'synthesis', label: 'AI-OS LINK ESTABLISHED', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(164.8);
    expect(freqs).toContain(220);
  });

  it('AUDIT CHAIN BROKEN plays a sustained tritone', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'synthesis', label: 'AUDIT CHAIN BROKEN', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(220);
    expect(freqs).toContain(311.1);
  });

  it('approval-required plays a suspended 2nd chord', () => {
    const mock = createMockAudioContext();
    boot(mock);
    const before = oscillatorNodes(mock).length;

    emitCognition({ type: 'approval-required', label: '', intensity: 1 });

    const freqs = lastOscillatorFrequencies(mock).slice(before);
    expect(freqs).toContain(220);
    expect(freqs).toContain(246.9);
    expect(freqs).toContain(329.6);
  });

  it('approval-resolved rejected ducks ambient gain and plays E2 thud', () => {
    const mock = createMockAudioContext();
    boot(mock);

    emitCognition({ type: 'approval-resolved', label: 'rejected', intensity: 1 });

    const ambDuck = mock.scheduled.find(
      (s) => s.method === 'setTargetAtTime' && s.args[0] === 0.015,
    );
    expect(ambDuck).toBeDefined();

    const freqs = lastOscillatorFrequencies(mock);
    expect(freqs).toContain(82.4);
  });
});

describe('generic knowledge-acquired tick', () => {
  beforeEach(() => {
    __resetSoundEngineForTests();
    capturedCallbacks.length = 0;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('staggers same-frame ticks instead of summing in phase', () => {
    const mock = createMockAudioContext();
    stubAudioContext(mock);
    startSound();

    emitCognition({ type: 'knowledge-acquired', label: 'Acquired trail A', intensity: 1 });
    emitCognition({ type: 'knowledge-acquired', label: 'Acquired trail B', intensity: 1 });
    emitCognition({ type: 'knowledge-acquired', label: 'Acquired trail C', intensity: 1 });

    const tickOscs = oscillatorNodes(mock).filter((n) => n.frequency?.value === 1318.5);
    expect(tickOscs.length).toBe(3);

    const startDelays = tickOscs.map((n) => {
      const startCall = n.start.mock.calls[0] as [number];
      return startCall[0];
    });
    expect(startDelays[1] - startDelays[0]).toBeCloseTo(0.045, 3);
    expect(startDelays[2] - startDelays[1]).toBeCloseTo(0.045, 3);
  });
});

describe('stopSound', () => {
  beforeEach(() => {
    __resetSoundEngineForTests();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('fades master, schedules oscillator stops, and closes after the fade', () => {
    const mock = createMockAudioContext();
    stubAudioContext(mock);
    startSound();

    expect(isSoundOn()).toBe(true);
    stopSound();
    expect(isSoundOn()).toBe(false);

    // master gain target fade to 0
    const masterGain = mock.nodes.find((n) => n.type === 'gain' && n.gain?.value === 0.5);
    expect(masterGain).toBeDefined();
    const fade = mock.scheduled.find(
      (s) => s.node === masterGain && s.method === 'setTargetAtTime' && s.args[0] === 0,
    );
    expect(fade).toBeDefined();

    // ambient oscillators scheduled to stop later
    const ambientOscs = oscillatorNodes(mock).filter(
      (n) => n.frequency?.value === 55 || n.frequency?.value === 165.6,
    );
    for (const osc of ambientOscs) {
      const stopCall = osc.stop.mock.calls[0] as [number];
      expect(stopCall[0]).toBeGreaterThan(mock.currentTime);
    }

    vi.advanceTimersByTime(400);
    expect(mock.close).toHaveBeenCalled();
  });
});

describe('state guards', () => {
  beforeEach(() => {
    __resetSoundEngineForTests();
    capturedCallbacks.length = 0;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('drops blips while the context is suspended', () => {
    const mock = createMockAudioContext();
    mock.state = 'suspended';
    stubAudioContext(mock);
    startSound();

    const before = oscillatorNodes(mock).length;
    emitCognition({ type: 'knowledge-acquired', label: 'Acquired trail', intensity: 1 });
    const after = oscillatorNodes(mock).length;

    expect(after).toBe(before);
  });

  it('is idempotent: startSound with an existing context does nothing', () => {
    const mock = createMockAudioContext();
    stubAudioContext(mock);
    startSound();
    const firstOscCount = oscillatorNodes(mock).length;

    startSound();
    const secondOscCount = oscillatorNodes(mock).length;

    expect(secondOscCount).toBe(firstOscCount);
  });

  it('does not throw if stopSound is called before startSound', () => {
    expect(() => stopSound()).not.toThrow();
    expect(isSoundOn()).toBe(false);
  });
});
