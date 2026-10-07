import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import MaterializationLayer from '../../superbrain/components/canvas/MaterializationLayer';
import { __resetAiosAdapterForTests, getPendingApproval, sendDirective } from '../../superbrain/lib/aiosAdapter';
import { dispatchLivingMirrorEvent } from '../../superbrain/lib/livingMirrorRegistry';
import { publishCognition, subscribeCognition } from '../../superbrain/lib/cognitionBus';
import { __resetCompletionReflexForTests } from '../../superbrain/lib/completionReflex';
import {
  __resetTabStoreForTests, claimWorkMaterialization, closeWorkspace, finishMaterializedTabRetraction,
  focusMaterializedTab, getTabStoreSnapshot, openWorkspacePanel, releaseWorkMaterialization,
  reopenMaterializedTab, setMaterializedTabLifecycle,
} from '../../superbrain/lib/tabStore';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { LivingWorkspaceShell } from '../LivingWorkspaceShell';

// Registry admission, transport/cache, MaterializationLayer effects, store,
// anchors and readable Shell are real. GPU leaves cannot mount in jsdom;
// these tests establish source/reader ownership, not native 3D acceptance.
vi.mock('../../superbrain/components/canvas/MaterializedTab', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/ReabsorptionParticles', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/AnatomicalConductorOverlay', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/AttentionConductionPulse', () => ({ default: () => null }));
vi.mock('../../superbrain/components/canvas/CompletionMemoryBead', () => ({ default: () => null }));

beforeEach(async () => {
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  __resetCompletionReflexForTests();
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/api/v1/auth/session')) {
      return new Response('{"authenticated":true}', { headers: { 'Content-Type': 'application/json' } });
    }
    if (String(url).endsWith('/api/generate')) {
      const prompt = JSON.parse(String(init?.body)).messages[0].content[0].text;
      if (prompt === 'hold a real approval fixture') {
        const permission = { text: 'Permission to create the bounded file', input: {
          approvalToken: 'pending-fixture-token', creations: [{ filepath: 'src/gated.py', content: 'print("proposal")' }],
        } };
        return new Response(`event: human_required\ndata: ${JSON.stringify(permission)}\n\n`, {
          headers: { 'Content-Type': 'text/event-stream' },
        });
      }
      const code = { code: prompt === 'empty legacy fixture' ? '' : 'print("foreign cache")', language: 'python', filepath: 'other/foreign.py' };
      return new Response(`event: code\ndata: ${JSON.stringify(code)}\n\nevent: done\ndata: {}\n\n`, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }
    return new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
  }));
  // The existing adapter reset intentionally leaves its legacy code singleton.
  // Establish an empty-code baseline through real transport, not an accessor mock.
  await sendDirective('empty legacy fixture');
});
afterEach(() => {
  cleanup();
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  __resetCompletionReflexForTests();
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  vi.unstubAllGlobals();
});

function mount(reducedMotion = false) {
  render(<><MaterializationLayer reducedMotion={reducedMotion} /><LivingWorkspaceShell experienceMode="beginner" /></>);
}
function emit(id: number, payload: Record<string, unknown>, replay = false) {
  return dispatchLivingMirrorEvent({ id, eventType: 'code', replay,
    canonical: { schemaVersion: '1.0', eventId: `event-${id}`, eventType: 'code', payload }, payload });
}
function contents() {
  return getTabStoreSnapshot().tabs.filter((tab) => tab.kind === 'content');
}
function read(id: string) {
  act(() => { setMaterializedTabLifecycle(id, 'live'); focusMaterializedTab(id); });
}

it.each([false, true])('materializes admitted mirror code even with an empty legacy cache (reduced motion: %s)', (reducedMotion) => {
  mount(reducedMotion);
  act(() => emit(100, { code: 'print("mirror owned")', language: 'python', filepath: 'src/mirror.py' }));
  expect(contents()).toHaveLength(1);
  expect(contents()[0].content).toMatchObject({ code: 'print("mirror owned")', language: 'python', filepath: 'src/mirror.py' });
  read(contents()[0].id);
  expect(screen.getByText('print("mirror owned")')).toBeVisible();
});

it('never fills an admitted mirror surface from a foreign request cache', async () => {
  await sendDirective('seed unrelated request');
  mount();
  act(() => emit(100, { code: 'print("mirror owned")', language: 'python', filepath: 'src/mirror.py' }));
  expect(contents()).toHaveLength(1);
  expect(contents()[0].content?.code).toBe('print("mirror owned")');
  expect(contents()[0].content?.filepath).toBe('src/mirror.py');
  expect(screen.queryByText('print("foreign cache")')).not.toBeInTheDocument();
});

it('keeps two pathless admitted results distinct without inventing a file path', () => {
  mount();
  act(() => {
    emit(100, { code: 'print("unnamed one")', language: 'python' });
    emit(101, { code: 'print("unnamed two")', language: 'python' });
  });
  expect(contents()).toHaveLength(2);
  expect(contents().map((tab) => tab.content?.filepath)).toEqual(['', '']);
  expect(new Set(contents().map((tab) => tab.id)).size).toBe(2);
  const first = contents()[0];
  const second = contents()[1];
  read(first.id);
  expect(screen.getByText('print("unnamed one")')).toBeVisible();
  read(second.id);
  expect(screen.getByText('print("unnamed two")')).toBeVisible();
  expect(screen.getByText('print("unnamed one")')).toBeInTheDocument();
});

it.each([undefined, '', 42, { code: 'not a string' }])('ignores malformed code before announcing or growing a surface (%j)', async (code) => {
  await sendDirective('seed unrelated request');
  mount();
  act(() => emit(100, code === undefined ? {} : { code, language: 'python' }));
  expect(contents()).toHaveLength(0);
  expect(useMirrorStore.getState().recentEvents).toHaveLength(0);
  expect(useMirrorStore.getState().lastAnnouncement).not.toMatch(/code emitted/i);
});

it('a metadata-only CODE EMITTED signal cannot materialize legacy cached code', async () => {
  await sendDirective('seed unrelated request');
  mount();
  act(() => publishCognition({ type: 'knowledge-acquired', label: 'CODE EMITTED', source: 'test-fixture' }));
  expect(contents()).toHaveLength(0);
});

it('historical, duplicate and out-of-order code cannot create another surface or replace the admitted reader', () => {
  mount();
  act(() => emit(90, { code: 'print("historical")', language: 'python', filepath: 'src/old.py' }, true));
  expect(contents()).toHaveLength(0);
  act(() => emit(100, { code: 'print("current")', language: 'python', filepath: 'src/current.py' }));
  expect(contents()).toHaveLength(1);
  const original = contents()[0];
  read(original.id);
  const reader = screen.getByText('print("current")');
  act(() => {
    emit(100, { code: 'print("duplicate")', language: 'python', filepath: 'src/current.py' });
    emit(99, { code: 'print("older")', language: 'python', filepath: 'src/current.py' });
  });
  expect(contents().map((tab) => tab.id)).toEqual([original.id]);
  expect(screen.getByText('print("current")')).toBe(reader);
});

it('same-path admitted refresh preserves reader, anatomical origin, scroll and current panel selection', () => {
  mount();
  act(() => emit(100, { code: 'print("first")', language: 'python', filepath: 'src/mirror.py' }));
  expect(contents()).toHaveLength(1);
  const original = contents()[0];
  read(original.id);
  const reader = screen.getByText('print("first")');
  const body = reader.closest<HTMLElement>('.lm-surface__body')!;
  body.scrollTop = 52;
  act(() => {
    openWorkspacePanel('history', 'Recent activity');
    emit(101, { code: 'print("updated")', language: 'python', filepath: 'src/mirror.py' });
  });
  expect(contents()).toHaveLength(1);
  expect(contents()[0]).toMatchObject({ id: original.id, seatIndex: original.seatIndex,
    originLocal: original.originLocal, targetLocal: original.targetLocal });
  expect(getTabStoreSnapshot().focusId).toBe('history');
  expect(screen.getByText('print("updated")')).toBe(reader);
  expect(body.scrollTop).toBe(52);
});

it('pathless Close/Reopen restores the same result, reader and reading context', () => {
  mount();
  act(() => emit(100, { code: 'print("unnamed")', language: 'python' }));
  expect(contents()).toHaveLength(1);
  const original = contents()[0];
  read(original.id);
  const reader = screen.getByText('print("unnamed")');
  reader.scrollTop = 37;
  act(() => {
    closeWorkspace(original.id);
    const closing = contents().find((tab) => tab.id === original.id)!;
    finishMaterializedTabRetraction(original.id, closing.retractionToken);
    reopenMaterializedTab(original.id);
  });
  read(original.id);
  expect(contents().map((tab) => tab.id)).toEqual([original.id]);
  expect(contents()[0].content?.filepath).toBe('');
  expect(screen.getByText('print("unnamed")')).toBe(reader);
  expect(reader.scrollTop).toBe(37);
});

it('respects the existing Chrome materialization claim without creating a duplicate', () => {
  mount();
  act(() => {
    claimWorkMaterialization();
    emit(100, { code: 'print("claimed")', language: 'python', filepath: 'src/mirror.py' });
  });
  expect(contents()).toHaveLength(0);
  act(() => {
    releaseWorkMaterialization();
    emit(101, { code: 'print("unclaimed")', language: 'python', filepath: 'src/mirror.py' });
  });
  expect(contents()).toHaveLength(1);
  expect(contents()[0].content?.code).toBe('print("unclaimed")');
});

it('carries only the admitted code, display metadata and cursor into the shared reaction', () => {
  const reactions: Record<string, unknown>[] = [];
  const unsubscribe = subscribeCognition((event) => {
    if (event.label === 'CODE EMITTED') reactions.push(event.data ?? {});
  });
  try {
    act(() => emit(100, { code: 'print("owned")', language: 'python', filepath: 'src/owned.py',
      approvalToken: 'private-capability', unrelated: { privateDetails: 'not-needed-by-scene' } }));
    expect(reactions).toEqual([{ code: 'print("owned")', language: 'python', filepath: 'src/owned.py', eventCursor: 100 }]);
  } finally { unsubscribe(); }
});

it('unnamed switcher controls keep stable local labels when another result closes', () => {
  mount();
  act(() => {
    emit(100, { code: 'print("first unnamed")', language: 'python' });
    emit(101, { code: 'print("second unnamed")', language: 'python' });
  });
  const first = contents()[0];
  const second = contents()[1];
  fireEvent.click(screen.getByRole('button', { name: 'Generated result 2' }));
  expect(getTabStoreSnapshot().focusId).toBe(second.id);
  expect(screen.getByRole('heading', { name: 'Generated result 2' })).toBeVisible();
  expect(screen.getByText('print("second unnamed")')).toBeVisible();
  act(() => {
    closeWorkspace(first.id);
    const closing = contents().find((tab) => tab.id === first.id)!;
    finishMaterializedTabRetraction(first.id, closing.retractionToken);
  });
  expect(screen.getByRole('button', { name: 'Generated result 2' })).toBeVisible();
  expect(getTabStoreSnapshot().focusId).toBe(second.id);
});

it('History names and reopens an unnamed result through real controls without changing its reader', () => {
  mount();
  act(() => emit(100, { code: 'print("unnamed recovery")', language: 'python' }));
  const original = contents()[0];
  read(original.id);
  const reader = screen.getByText('print("unnamed recovery")');
  reader.scrollTop = 41;
  act(() => {
    closeWorkspace(original.id);
    const closing = contents().find((tab) => tab.id === original.id)!;
    finishMaterializedTabRetraction(original.id, closing.retractionToken);
  });
  fireEvent.click(screen.getByRole('button', { name: 'Recent activity' }));
  expect(screen.getByRole('button', { name: 'Forget Generated result 1' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Reopen Generated result 1' }));
  expect(getTabStoreSnapshot().focusId).toBe(original.id);
  expect(screen.getByRole('heading', { name: 'Generated result 1' })).toBeVisible();
  expect(screen.getByText('print("unnamed recovery")')).toBe(reader);
  expect(reader.scrollTop).toBe(41);
});

it.each([undefined, 'src/unrelated.py', 'src/gated.py'])('code evidence alone cannot dismiss or take the seat of pending permission (path: %s)', async (filepath) => {
  mount();
  await act(async () => { await sendDirective('hold a real approval fixture'); });
  const approval = getTabStoreSnapshot().tabs.find((tab) => tab.kind === 'approval')!;
  expect(approval).toBeDefined();
  const decision = screen.getByRole('button', { name: 'Approval review' });
  act(() => emit(100, { code: 'print("admitted but not permission")', language: 'python', ...(filepath ? { filepath } : {}) }));
  const held = getTabStoreSnapshot().tabs.find((tab) => tab.id === approval.id)!;
  expect(held.lifecycle).not.toBe('retracting');
  expect(getTabStoreSnapshot().focusId).toBe(approval.id);
  expect(contents()[0].seatIndex).not.toBe(approval.seatIndex);
  expect(getPendingApproval()?.token).toBe('pending-fixture-token');
  expect(screen.getByRole('button', { name: 'Approval review' })).toBe(decision);
  expect(decision).toBeVisible();
});

it.each([false, true])('late mirror refresh cannot reopen explicitly closed work (retirement finished: %s)', (finished) => {
  mount();
  act(() => emit(100, { code: 'print("first result")', language: 'python', filepath: 'src/mirror.py' }));
  const original = contents()[0];
  read(original.id);
  const reader = screen.getByText('print("first result")');
  reader.scrollTop = 67;
  act(() => {
    closeWorkspace(original.id);
    if (finished) {
      const closing = contents().find((tab) => tab.id === original.id)!;
      finishMaterializedTabRetraction(original.id, closing.retractionToken);
    }
    openWorkspacePanel('history', 'Recent activity');
    emit(101, { code: 'print("late result")', language: 'python', filepath: 'src/mirror.py' });
  });
  expect(contents().filter((tab) => tab.lifecycle !== 'retracting')).toHaveLength(0);
  expect(getTabStoreSnapshot().focusId).toBe('history');
  expect(getTabStoreSnapshot().recoverableTabs?.find((tab) => tab.id === original.id)?.content?.code).toBe('print("late result")');
  fireEvent.click(screen.getByRole('button', { name: 'Reopen src/mirror.py' }));
  expect(contents().map((tab) => tab.id)).toEqual([original.id]);
  expect(screen.getByText('print("late result")')).toBe(reader);
  expect(reader.scrollTop).toBe(67);
});

it('keeps overflow code readable without assigning another result to an occupied body seat', () => {
  mount();
  act(() => {
    for (let index = 0; index < 13; index++) {
      emit(100 + index, { code: `// unnamed result ${index + 1}`, language: 'text' });
    }
  });
  expect(contents()).toHaveLength(13);
  const seated = contents().filter((tab) => tab.seatIndex !== null);
  expect(seated).toHaveLength(12);
  expect(new Set(seated.map((tab) => tab.seatIndex)).size).toBe(12);
  const overflow = contents()[12];
  expect(overflow).toMatchObject({ seatIndex: null, recoverySeatPending: true });
  fireEvent.click(screen.getByRole('button', { name: 'All 13 workspaces' }));
  fireEvent.click(screen.getByRole('button', { name: 'Generated result 13 · Anchor unassigned' }));
  expect(screen.getByText('// unnamed result 13')).toBeVisible();
  expect(screen.getByText(/No free body anchor/)).toBeVisible();
  const reader = screen.getByText('// unnamed result 13');
  const first = contents()[0];
  act(() => {
    closeWorkspace(first.id);
    const closing = contents().find((tab) => tab.id === first.id)!;
    finishMaterializedTabRetraction(first.id, closing.retractionToken);
    focusMaterializedTab(overflow.id);
  });
  expect(contents().find((tab) => tab.id === overflow.id)).toMatchObject({ seatIndex: first.seatIndex, recoverySeatPending: false });
  expect(screen.getByText('// unnamed result 13')).toBe(reader);
  expect(reader).toBeVisible();
});
