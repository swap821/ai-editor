import { forwardRef, useImperativeHandle } from 'react';
import { render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BodySpeech from './BodySpeech';

const h = vi.hoisted(() => ({
  frame: { cb: null as null | (() => void) },
  fake: {
    text: '',
    fillOpacity: 0,
    outlineOpacity: 0,
    textRenderInfo: null as null | { parameters: { text: string } },
    sync: vi.fn<(cb?: () => void) => void>(),
    _isSyncing: false,
    _needsSync: false,
    _queuedSyncs: null as unknown[] | null,
  },
  getReplyVoice: vi.fn(),
  deriveBodySpeech: vi.fn(),
  decideBodySpeechSync: vi.fn(),
  useReducedMotion: vi.fn(),
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: (cb: () => void) => {
    h.frame.cb = cb;
  },
}));

vi.mock('@react-three/drei', () => ({
  Text: forwardRef((_props: object, ref) => {
    useImperativeHandle(ref, () => h.fake);
    return null;
  }),
  Billboard: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
}));

vi.mock('@/lib/replyVoiceBus', () => ({ getReplyVoice: h.getReplyVoice }));
vi.mock('@/lib/bodySpeech', () => ({
  deriveBodySpeech: h.deriveBodySpeech,
  decideBodySpeechSync: h.decideBodySpeechSync,
}));
vi.mock('@/lib/reducedMotion', () => ({ useReducedMotion: h.useReducedMotion }));

function runFrame() {
  const cb = h.frame.cb;
  if (!cb) throw new Error('useFrame callback was not registered');
  cb();
}

function active(visibleText: string, fade = 0, glow = 0) {
  return { active: true, visibleText, fade, glow };
}

function groupOf(container: HTMLElement) {
  return container.querySelector('group') as unknown as { visible: boolean };
}

describe('BodySpeech', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(performance, 'now').mockReturnValue(1500);
    h.frame.cb = null;
    Object.assign(h.fake, {
      text: '',
      fillOpacity: 0,
      outlineOpacity: 0,
      textRenderInfo: null,
      _isSyncing: false,
      _needsSync: false,
      _queuedSyncs: null,
    });
    h.fake.sync.mockReset();
    h.getReplyVoice.mockReset().mockReturnValue({ text: 'hello', phase: 'speaking', since: 1000 });
    h.deriveBodySpeech.mockReset();
    h.decideBodySpeechSync.mockReset();
    h.useReducedMotion.mockReset().mockReturnValue(true);
  });

  afterEach(() => vi.restoreAllMocks());

  it('shows the group and writes text and opacity when active, hides it when not', () => {
    const { container } = render(<BodySpeech />);
    h.deriveBodySpeech.mockReturnValue(active('hello', 0.2, 0.5));
    h.decideBodySpeechSync.mockReturnValue('sync');
    runFrame();

    expect(h.deriveBodySpeech).toHaveBeenCalledWith(
      expect.objectContaining({ text: 'hello', phase: 'speaking', sinceMs: 500, reducedMotion: true }),
    );
    expect(h.decideBodySpeechSync.mock.calls[0].slice(0, 3)).toEqual(['hello', '', false]);
    expect(groupOf(container).visible).toBe(true);
    expect(h.fake.text).toBe('hello');
    expect(h.fake.sync).toHaveBeenCalledTimes(1);
    expect(h.fake.fillOpacity).toBeCloseTo(0.6);
    expect(h.fake.outlineOpacity).toBeCloseTo(0.36);

    h.deriveBodySpeech.mockReturnValue({ active: false, visibleText: '', fade: 1, glow: 0 });
    runFrame();
    expect(groupOf(container).visible).toBe(false);
    expect(h.fake.sync).toHaveBeenCalledTimes(1);
  });

  it('does not sync when the decision is skip', () => {
    render(<BodySpeech />);
    h.deriveBodySpeech.mockReturnValue(active('hello'));
    h.decideBodySpeechSync.mockReturnValue('skip');
    runFrame();

    expect(h.fake.sync).not.toHaveBeenCalled();
    expect(h.fake.text).toBe('');
    expect(h.fake.fillOpacity).toBeCloseTo(0.5);
  });

  it('resets troika internals on force-resync and only the latest callback clears the pending flag', () => {
    render(<BodySpeech />);
    h.fake._isSyncing = true;
    h.fake._needsSync = false;
    h.fake._queuedSyncs = [1];
    h.deriveBodySpeech.mockReturnValue(active('hello'));

    h.decideBodySpeechSync.mockReturnValue('sync');
    runFrame();
    h.decideBodySpeechSync.mockReturnValue('force-resync');
    runFrame();

    expect(h.fake._isSyncing).toBe(false);
    expect(h.fake._needsSync).toBe(true);
    expect(h.fake._queuedSyncs).toBeNull();
    expect(h.fake.sync).toHaveBeenCalledTimes(2);
    const [first, second] = h.fake.sync.mock.calls.map((c) => c[0] as () => void);

    h.decideBodySpeechSync.mockReturnValue('skip');
    first();
    runFrame();
    expect(h.decideBodySpeechSync.mock.calls[2][2]).toBe(true);

    second();
    runFrame();
    expect(h.decideBodySpeechSync.mock.calls[3][2]).toBe(false);
  });

  it('forces a resync when rendered geometry is stale for already-synced text', () => {
    render(<BodySpeech />);
    h.deriveBodySpeech.mockReturnValue(active('hello'));
    h.decideBodySpeechSync.mockReturnValue('sync');
    runFrame();
    (h.fake.sync.mock.calls[0][0] as () => void)();

    h.fake.textRenderInfo = { parameters: { text: 'hel' } };
    h.decideBodySpeechSync.mockReturnValue('skip');
    runFrame();

    expect(h.decideBodySpeechSync).toHaveBeenCalledTimes(1);
    expect(h.fake.sync).toHaveBeenCalledTimes(2);
    expect(h.fake._needsSync).toBe(true);
  });
});
