import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MaterializationLayer from '../../superbrain/components/canvas/MaterializationLayer';
import { publishCognition } from '../../superbrain/lib/cognitionBus';
import { __resetCompletionReflexForTests, getCompletionReflexSnapshot } from '../../superbrain/lib/completionReflex';
import {
  __resetTabStoreForTests, closeWorkspace, focusWorkspace, getTabStoreSnapshot,
  openWorkspacePanel, pinWorkspace, setMaterializedTabLifecycle, showContentSurface,
} from '../../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from '../LivingWorkspaceShell';

// Keep the real lifecycle/attention owners, completion timer and readable DOM.
// GPU children cannot mount in jsdom; these tests make no rendering claim.
vi.mock('../../superbrain/components/canvas/MaterializedTab', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/ReabsorptionParticles', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/AnatomicalConductorOverlay', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/AttentionConductionPulse', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/CompletionMemoryBead', () => ({ default: () => null }));

beforeEach(() => {
  __resetTabStoreForTests();
  __resetCompletionReflexForTests();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
});
afterEach(() => {
  cleanup();
  __resetTabStoreForTests();
  __resetCompletionReflexForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

async function mount(reducedMotion = false) {
  vi.useFakeTimers();
  await act(async () => {
    render(<><MaterializationLayer reducedMotion={reducedMotion} /><LivingWorkspaceShell experienceMode="expert" /></>);
  });
}

function result() {
  const tab = showContentSurface({ filepath: 'result.py', language: 'python', code: 'print("retained result")', verifyOutput: 'Reported check output' }, {
    seatIndex: 2, originLocal: [0, 0.2, 0.4], targetLocal: [1, 0.2, 0.4],
  });
  setMaterializedTabLifecycle(tab.id, 'live');
  return tab;
}

it.each([false, true])('completion does not dismiss the result being read (reduced motion: %s)', async (reducedMotion) => {
  await mount(reducedMotion);
  let id = '';
  act(() => { id = result().id; });
  const text = screen.getByText('print("retained result")');
  const body = text.closest<HTMLElement>('.lm-surface__body')!;
  body.scrollTop = 90;
  text.focus();
  act(() => {
    publishCognition({ type: 'knowledge-acquired', label: 'VERIFICATION GREEN', source: 'test-fixture' });
    vi.advanceTimersByTime(2200);
  });
  expect(screen.getByText('print("retained result")')).toBe(text);
  expect(text).toBeVisible();
  expect(text).toHaveFocus();
  expect(body.scrollTop).toBe(90);
  expect(getTabStoreSnapshot()).toMatchObject({ focusId: id, tabs: [{ id, lifecycle: 'live', seatIndex: 2 }] });
  expect(getCompletionReflexSnapshot().state).toBe('settling');
});

it('keeps a pinned background result reachable after completion and retracts only on explicit dismissal', async () => {
  await mount();
  let id = '';
  act(() => { id = result().id; pinWorkspace(id); });
  const text = screen.getByText('print("retained result")');
  act(() => publishCognition({ type: 'knowledge-acquired', label: 'VERIFICATION GREEN', source: 'test-fixture' }));
  act(() => { openWorkspacePanel('history', 'Recent observations'); vi.advanceTimersByTime(2200); });
  expect(text).toBeInTheDocument();
  expect(text).not.toBeVisible();
  act(() => focusWorkspace(id));
  expect(screen.getByText('print("retained result")')).toBe(text);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id, lifecycle: 'live', pinned: true });
  act(() => closeWorkspace(id));
  expect(text).toBeInTheDocument();
  expect(text).not.toBeVisible();
  expect(getTabStoreSnapshot().recoverableTabs?.[0].id).toBe(id);
  expect(getTabStoreSnapshot().tabs[0].lifecycle).toBe('retracting');
  expect(getCompletionReflexSnapshot().state).toBe('reabsorbing');
});

it('content refresh preserves the established anatomical origin and readable DOM instance', async () => {
  await mount();
  let id = '';
  act(() => { id = result().id; });
  const text = screen.getByText('print("retained result")');
  const body = text.closest<HTMLElement>('.lm-surface__body')!;
  body.scrollTop = 60;
  text.focus();
  act(() => showContentSurface({ filepath: 'result.py', language: 'python', code: 'print("next chunk")', streaming: true }, {
    seatIndex: 3, originLocal: [0, -0.4, 0.5], targetLocal: [1.2, -0.4, 0.5],
  }));
  expect(getTabStoreSnapshot().tabs).toMatchObject([{ id, seatIndex: 2, originLocal: [0, 0.2, 0.4], targetLocal: [1, 0.2, 0.4] }]);
  expect(screen.getByText('print("next chunk")')).toBe(text);
  expect(text).toHaveFocus();
  expect(body.scrollTop).toBe(60);
});

it('a content upsert does not cancel the current attention transfer or steal panel focus', async () => {
  await mount();
  let id = '';
  act(() => {
    id = result().id;
    const other = showContentSurface({ filepath: 'other.py', language: 'python', code: 'other' }, { seatIndex: 3 });
    focusWorkspace(other.id);
    focusWorkspace(id);
  });
  const transfer = getTabStoreSnapshot().attention;
  act(() => showContentSurface({ filepath: 'other.py', language: 'python', code: 'background update' }));
  expect(getTabStoreSnapshot().attention).toBe(transfer);
  expect(getTabStoreSnapshot().focusId).toBe(id);
  act(() => openWorkspacePanel('history', 'Recent observations'));
  act(() => showContentSurface({ filepath: 'result.py', language: 'python', code: 'new result' }));
  expect(getTabStoreSnapshot().focusId).toBe('history');
});
