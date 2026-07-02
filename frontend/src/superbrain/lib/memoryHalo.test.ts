/** B4 — the memory halo's brain: lifecycle, sync, orbit determinism. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('./aiosAdapter', () => ({
  fetchPendingFacts: vi.fn(async () => []),
  approveFactProposal: vi.fn(async () => 'approved'),
  rejectFactProposal: vi.fn(async () => true),
}));

import { approveFactProposal, rejectFactProposal, type FactProposal } from './aiosAdapter';
import {
  __resetHaloForTests,
  absorbMote,
  dismissPresentation,
  getHalo,
  moteOrbitOffset,
  presentMote,
  releaseMote,
  retireMote,
  settleFlare,
  stampLifecycle,
  syncProposals,
} from './memoryHalo';

const approveMock = vi.mocked(approveFactProposal);
const rejectMock = vi.mocked(rejectFactProposal);

function proposal(id: number): FactProposal {
  return { id, subject: 'operator', predicate: 'prefers', object: `thing-${id}`, source: 'auto-extract' };
}

beforeEach(() => {
  __resetHaloForTests();
  approveMock.mockClear();
  approveMock.mockResolvedValue('approved');
  rejectMock.mockClear();
  rejectMock.mockResolvedValue(true);
});

describe('syncProposals', () => {
  it('births unknown proposals as orbiting motes with deterministic seeds', () => {
    syncProposals([proposal(1), proposal(2)]);
    const [a, b] = getHalo().motes;
    expect(a.lifecycle).toBe('orbiting');
    expect(b.lifecycle).toBe('orbiting');
    expect(a.seed).not.toBe(b.seed);

    __resetHaloForTests();
    syncProposals([proposal(1)]);
    expect(getHalo().motes[0].seed).toBe(a.seed); // same id → same seed, every session
  });

  it('a poll never snaps a known mote out of its lifecycle', () => {
    syncProposals([proposal(1)]);
    presentMote(1);
    syncProposals([proposal(1)]);
    expect(getHalo().motes[0].lifecycle).toBe('presenting');
    expect(getHalo().presentingId).toBe(1);
  });

  it('drops server-resolved motes unless their exit animation is mid-flight', () => {
    syncProposals([proposal(1), proposal(2)]);
    void absorbMote(1); // async — lifecycle set synchronously
    syncProposals([proposal(2)]);
    const ids = getHalo().motes.map((mote) => mote.proposal.id);
    expect(ids).toContain(1); // absorbing → survives until retired
    expect(ids).toContain(2);

    syncProposals([]); // 2 vanished while merely orbiting → dropped
    expect(getHalo().motes.map((mote) => mote.proposal.id)).toEqual([1]);
  });
});

describe('presentation', () => {
  it('presents one mote at a time and dismisses back to orbit', () => {
    syncProposals([proposal(1), proposal(2)]);
    presentMote(1);
    presentMote(2);
    const state = getHalo();
    expect(state.presentingId).toBe(2);
    expect(state.motes.find((m) => m.proposal.id === 1)?.lifecycle).toBe('orbiting');
    expect(state.motes.find((m) => m.proposal.id === 2)?.lifecycle).toBe('presenting');

    dismissPresentation();
    expect(getHalo().presentingId).toBeNull();
    expect(getHalo().motes.every((m) => m.lifecycle === 'orbiting')).toBe(true);
  });
});

describe('resolution', () => {
  it('absorb approves through the backend and leaves the animation to retire it', async () => {
    syncProposals([proposal(1)]);
    await absorbMote(1);
    expect(approveMock).toHaveBeenCalledWith(1);
    expect(getHalo().motes[0].lifecycle).toBe('absorbing');
    retireMote(1);
    expect(getHalo().motes).toEqual([]);
  });

  it('a contradiction flares and then settles back to orbit — still pending', async () => {
    approveMock.mockResolvedValueOnce('contradiction');
    syncProposals([proposal(1)]);
    await absorbMote(1);
    expect(getHalo().motes[0].lifecycle).toBe('flaring');
    settleFlare(1);
    expect(getHalo().motes[0].lifecycle).toBe('orbiting');
  });

  it('a failed approve returns the mote to orbit unchanged', async () => {
    approveMock.mockResolvedValueOnce('failed');
    syncProposals([proposal(1)]);
    await absorbMote(1);
    expect(getHalo().motes[0].lifecycle).toBe('orbiting');
  });

  it('release rejects through the backend; a failed reject restores orbit', async () => {
    syncProposals([proposal(1), proposal(2)]);
    await releaseMote(1);
    expect(rejectMock).toHaveBeenCalledWith(1);
    expect(getHalo().motes.find((m) => m.proposal.id === 1)?.lifecycle).toBe('releasing');

    rejectMock.mockResolvedValueOnce(false);
    await releaseMote(2);
    expect(getHalo().motes.find((m) => m.proposal.id === 2)?.lifecycle).toBe('orbiting');
  });
});

describe('clock stamping', () => {
  it('stamps only unstamped lifecycles', () => {
    syncProposals([proposal(1)]);
    stampLifecycle(1, 12.5);
    expect(getHalo().motes[0].lifecycleAt).toBe(12.5);
    stampLifecycle(1, 99);
    expect(getHalo().motes[0].lifecycleAt).toBe(12.5);
  });
});

describe('moteOrbitOffset', () => {
  it('is deterministic and bounded', () => {
    const a = moteOrbitOffset(1.2, 10, false);
    const b = moteOrbitOffset(1.2, 10, false);
    expect(a).toEqual(b);
    const radius = Math.hypot(a[0], a[2]);
    expect(radius).toBeGreaterThan(0.25);
    expect(radius).toBeLessThan(0.75);
  });

  it('reduced motion pins a static constellation (time-invariant)', () => {
    expect(moteOrbitOffset(2.4, 0, true)).toEqual(moteOrbitOffset(2.4, 500, true));
    expect(moteOrbitOffset(2.4, 0, false)).not.toEqual(moteOrbitOffset(2.4, 500, false));
  });
});
