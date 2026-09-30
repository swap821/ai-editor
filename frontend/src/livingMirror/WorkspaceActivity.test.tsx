import { act, cleanup, render } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import EcosystemDashboard from '../workbench/EcosystemDashboard';
import VultureFeed from '../workbench/VultureFeed';
import CouncilDashboard from '../workbench/CouncilDashboard';
import { WorkspaceActivityContext } from './WorkspaceActivityContext';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('retained workspace periodic reads', () => {
  it.each([
    ['ecosystem', EcosystemDashboard],
    ['scanner', VultureFeed],
    ['council', CouncilDashboard],
  ] as const)('pauses %s polling while hidden and resumes when visible', async (_name, Panel) => {
    vi.useFakeTimers();
    const read = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => url.includes('/council/missions') ? { count: 0, missions: [] } : {
        vulture: { available: true, lastScan: null },
        ecosystem: { available: true, lastScan: null },
        constitution: { casteCount: 7, frozenCoreProtected: true },
        symbolRepoMap: { activation: 'proposal/evidence', lastScan: null },
        metaLoop: { safetyStatus: 'ok', proposalCount: 0 },
        councilMemory: { deliberationCount: 0 },
      },
    }));
    vi.stubGlobal('fetch', read);
    const view = render(<WorkspaceActivityContext.Provider value={true}><Panel /></WorkspaceActivityContext.Provider>);
    await act(async () => {});
    const firstReadCount = read.mock.calls.length;
    expect(firstReadCount).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(read.mock.calls.length).toBeGreaterThan(firstReadCount);

    view.rerender(<WorkspaceActivityContext.Provider value={false}><Panel /></WorkspaceActivityContext.Provider>);
    const hiddenReadCount = read.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(60000); });
    expect(read.mock.calls.length).toBe(hiddenReadCount);
    view.rerender(<WorkspaceActivityContext.Provider value={true}><Panel /></WorkspaceActivityContext.Provider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(read.mock.calls.length).toBeGreaterThan(hiddenReadCount);
  });
});
