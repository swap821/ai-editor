import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { readLivingMirrorStylesheet } from '../test/livingMirrorStylesheet';
import GagosChrome from '../workbench/GagosChrome';
import * as store from '../superbrain/lib/tabStore';
import { LivingWorkspaceShell } from './LivingWorkspaceShell';
import { __resetSovereignIdentityForTests, refreshSovereignStatus } from '../superbrain/lib/sovereignIdentity';
import { publishCognition } from '../superbrain/lib/cognitionBus';
import { useCognitionBus } from '../workbench/hooks/useCognitionBus';
import { setRendererFallbackPresentation } from './rendererFallbackPresentation';

// Real store, shell, persistent DOM and identity boundary. Only HTTP is external.
beforeEach(() => {
  store.__resetTabStoreForTests();
  __resetSovereignIdentityForTests();
  setRendererFallbackPresentation(false);
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
});
afterEach(() => { cleanup(); store.__resetTabStoreForTests(); __resetSovereignIdentityForTests(); setRendererFallbackPresentation(false); vi.unstubAllGlobals(); });

function materialize(filepath = 'result.ts', code = 'readable result') {
  const tab = store.showContentSurface({ filepath, code, language: 'typescript', verifyVerdict: 'fail', verifyOutput: 'Reported failure' },
    { seatIndex: 2, originLocal: [1, 2, 3], targetLocal: [4, 5, 6] });
  store.setMaterializedTabLifecycle(tab.id, 'live');
  return tab;
}
function finishRetraction(id: string) {
  const token = store.getTabStoreSnapshot().tabs.find((tab) => tab.id === id)?.retractionToken;
  store.finishMaterializedTabRetraction(id, token);
}
function recent(mode: 'beginner' | 'expert' = 'expert') {
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' }))
    .getByRole('button', { name: mode === 'beginner' ? 'Recent activity' : 'Recent observations' }));
}

it.each(['beginner', 'expert'] as const)('keeps the same reading DOM through Close, completed retraction and Reopen in %s', async (mode) => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode={mode} />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); });
  const output = screen.getByText('readable result');
  const body = output.closest<HTMLElement>('.lm-surface__body')!;
  body.scrollTop = 72;
  fireEvent.scroll(body);
  fireEvent.click(screen.getByText('Reported check output'));
  const disclosure = screen.getByText('Reported check output').closest('details')!;
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  expect(output).toBeInTheDocument();
  expect(output).not.toBeVisible();
  expect(store.getTabStoreSnapshot().recoverableTabs?.map((saved) => saved.id)).toEqual([tab.id]);
  recent(mode); // The still-retracting result reserves its original seat.
  act(() => finishRetraction(tab.id));
  expect(store.getTabStoreSnapshot().tabs.some((record) => record.id === tab.id)).toBe(false);
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
  expect(store.getTabStoreSnapshot().focusId).toBe(tab.id);
  const reopened = store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)!;
  expect([reopened.seatIndex, reopened.bornAt, reopened.originLocal, reopened.targetLocal])
    .toEqual([2, tab.bornAt, [1, 2, 3], [4, 5, 6]]);
  expect(screen.getByText('readable result')).toBe(output);
  expect(body.scrollTop).toBe(72);
  expect(disclosure).toHaveAttribute('open');
  expect(screen.getByRole('heading', { name: 'result.ts' })).toHaveFocus();
  expect(reopened.content?.verifyVerdict).toBe('fail');
});

it('uses a free anchor when the previous seat was claimed, without changing artifact identity', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
  recent(); // History now occupies the freed seat 2.
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)).toMatchObject({ seatIndex: 3, bornAt: tab.bornAt });
  expect(store.getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history')?.seatIndex).toBe(2);
  expect(screen.getByText('readable result')).toBeVisible();
});

it('keeps a saved result recoverable if all anatomical seats are occupied', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  act(() => { const tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
  recent();
  act(() => {
    for (let n = 0; n < 11; n++) store.openWorkspacePanel(`slot-${n}`, `Other workspace ${n}`);
    store.focusWorkspace('history');
  });
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
  expect(store.getTabStoreSnapshot().focusId).toBe('history');
  expect(store.getTabStoreSnapshot().recoverableTabs).toHaveLength(1);
  expect(screen.getByText(/All workspace anchors are in use/)).toBeVisible();
});

it('keeps the full late-growing result available without stealing focus or aliasing the history anchor', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
  recent();
  act(() => store.updateMaterializedTab(tab.id, {
    content: { filepath: 'result.ts', language: 'typescript', code: 'x'.repeat(3 * 1024 * 1024), streaming: true },
  }));
  expect(store.getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
  expect(store.getTabStoreSnapshot().focusId).toBe('history');
  const returned = store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)!;
  expect(returned.content?.code.length).toBe(3 * 1024 * 1024);
  expect(returned.seatIndex).toBe(3); // History has 2; never silently overlap it.
  act(() => store.focusWorkspace(tab.id));
  expect(screen.getByRole('heading', { name: 'result.ts' })).toBeVisible();
});

it('reopens the retained reading surface in narrow Guided/reduced-motion without a backend or GPU', async () => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query === '(max-width: 767px)' || query.includes('prefers-reduced-motion'),
    media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
  await act(async () => { render(<LivingWorkspaceShell experienceMode="beginner" />); });
  act(() => { const tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
  recent('beginner');
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
  expect(screen.getByText('readable result')).toBeVisible();
  expect(screen.getByRole('heading', { name: 'result.ts' })).toHaveFocus();
});

it('keeps oversized late work readable with no free anchor, then connects it on explicit focus after a seat is freed', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
  recent();
  act(() => {
    for (let n = 0; n < 11; n++) store.openWorkspacePanel(`slot-${n}`, `Other workspace ${n}`);
    store.focusWorkspace('history');
    store.updateMaterializedTab(tab.id, {
      content: { filepath: 'result.ts', language: 'typescript', code: 'x'.repeat(3 * 1024 * 1024) },
    });
  });
  expect(store.getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id))
    .toMatchObject({ seatIndex: null, recoverySeatPending: true });
  act(() => store.focusWorkspace(tab.id));
  expect(screen.getByRole('heading', { name: 'result.ts' })).toBeVisible();
  expect(screen.getByText(/No free body anchor/)).toBeVisible();
  const output = document.querySelector('.lm-artifact');
  expect(output?.textContent?.length).toBe(3 * 1024 * 1024);
  act(() => { store.closeWorkspace('slot-0'); store.focusWorkspace(tab.id); });
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id))
    .toMatchObject({ seatIndex: 3, recoverySeatPending: false });
  expect(document.querySelector('.lm-artifact')).toBe(output);
});

it('interrupts retraction without letting a stale renderer completion remove reopened work', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); store.closeWorkspace(tab.id); });
  recent();
  const reopen = screen.getByRole('button', { name: 'Reopen result.ts' });
  const firstToken = store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.retractionToken;
  fireEvent.click(reopen);
  act(() => store.finishMaterializedTabRetraction(tab.id, firstToken));
  expect(screen.getByText('readable result')).toBeVisible();
  act(() => store.closeWorkspace(tab.id));
  const secondToken = store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.retractionToken;
  expect(secondToken).not.toBe(firstToken);
  act(() => store.finishMaterializedTabRetraction(tab.id, firstToken));
  expect(store.getTabStoreSnapshot().tabs.some((record) => record.id === tab.id)).toBe(true);
  act(() => store.finishMaterializedTabRetraction(tab.id, secondToken));
  expect(store.getTabStoreSnapshot().recoverableTabs?.[0].content?.code).toBe('readable result');
});

it('requires explicit confirmation to Forget a closed browser copy and leaves other work intact', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let first!: ReturnType<typeof materialize>;
  act(() => { first = materialize(); store.closeWorkspace(first.id); });
  recent();
  fireEvent.click(screen.getByRole('button', { name: 'Forget result.ts' }));
  expect(store.getTabStoreSnapshot().recoverableTabs?.some((tab) => tab.id === first.id)).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Cancel forgetting' }));
  expect(screen.getByRole('button', { name: 'Reopen result.ts' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Forget result.ts' }));
  fireEvent.click(screen.getByRole('button', { name: 'Forget permanently' }));
  expect(screen.queryByRole('button', { name: 'Reopen result.ts' })).not.toBeInTheDocument();
  expect(screen.queryByText('readable result')).not.toBeInTheDocument();
  expect(store.getTabStoreSnapshot().focusId).toBe('history');
});

it('keeps the thirteenth result open when closed-result capacity is full rather than evicting saved work', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  act(() => {
    for (let n = 0; n < 12; n++) {
      const tab = materialize(`saved-${n}.ts`, `saved content ${n}`);
      store.closeWorkspace(tab.id);
    }
    materialize('current.ts', 'keep current readable');
  });
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  expect(screen.getByText('keep current readable')).toBeVisible();
  expect(store.getTabStoreSnapshot().recoverableTabs).toHaveLength(12);
  expect(store.getTabStoreSnapshot().recoverableTabs?.[0].content?.code).toBe('saved content 0');
  expect(screen.getByRole('status', { name: 'Result recovery' })).toHaveTextContent('remains open');
});

it('rejects oversized retention without truncating the result or changing its focus', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize('large.ts', 'x'.repeat(3 * 1024 * 1024)); });
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  expect(store.getTabStoreSnapshot().focusId).toBe(tab.id);
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.content?.code.length).toBe(3 * 1024 * 1024);
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.lifecycle).toBe('live');
  expect(store.getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
});

it('keeps late content updates while closed and releases only the intended artifact on explicit clear', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  let tab!: ReturnType<typeof materialize>;
  act(() => { tab = materialize(); store.closeWorkspace(tab.id); });
  recent();
  expect(screen.getByRole('button', { name: 'Reopen result.ts' })).toBeInTheDocument();
  act(() => {
    finishRetraction(tab.id);
    store.updateMaterializedTab(tab.id, { content: { filepath: 'result.ts', language: 'typescript', code: 'late final code', streaming: false } });
  });
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
  expect(screen.getByText('late final code')).toBeVisible();
  expect(store.getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.content?.verifyVerdict).toBeUndefined();
  act(() => { store.closeWorkspace(tab.id); store.clearMaterializedTab(); });
  expect(store.getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
  expect(screen.queryByText('late final code')).not.toBeInTheDocument();
});

it('preserves closed results through unknown identity but clears them on a measured owner change', async () => {
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ authenticated: true, operatorId: 'operator-a' }) } as Response);
  await refreshSovereignStatus();
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  act(() => { const tab = materialize(); store.closeWorkspace(tab.id); });
  recent();
  expect(screen.getByRole('button', { name: 'Reopen result.ts' })).toBeInTheDocument();
  vi.mocked(fetch).mockRejectedValueOnce(new Error('offline'));
  await act(async () => { await refreshSovereignStatus(); });
  expect(screen.getByRole('button', { name: 'Reopen result.ts' })).toBeInTheDocument();
  vi.mocked(fetch).mockResolvedValueOnce({ ok: true, json: async () => ({ authenticated: true, operatorId: 'operator-b' }) } as Response);
  await act(async () => { await refreshSovereignStatus(); });
  expect(store.getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
  expect(screen.queryByText('readable result')).not.toBeInTheDocument();
});

it('makes recovery reachable from Guided conversation under the real production stylesheet', async () => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: query === '(min-width: 768px)', media: query,
    addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
  const style = document.createElement('style');
  style.textContent = readLivingMirrorStylesheet();
  document.head.append(style);
  try {
    await act(async () => { render(<div className="lm-app" data-working="false">
      <GagosChrome integrated experienceMode="beginner" />
      <LivingWorkspaceShell experienceMode="beginner" />
    </div>); });
    act(() => { const tab = materialize(); store.closeWorkspace(tab.id); finishRetraction(tab.id); });
    // The shell's Guided nav is intentionally display:none. A recovery action
    // must be reachable through the real conversation, not that hidden nav.
    fireEvent.click(within(screen.getByRole('region', { name: 'Conversation' }))
      .getByRole('button', { name: 'Recent activity' }));
    fireEvent.click(screen.getByRole('button', { name: 'Reopen result.ts' }));
    expect(screen.getByText('readable result')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'result.ts' })).toHaveFocus();
  } finally { style.remove(); }
});

it.each([false, true])('routes late verification to the closed result, never the focused other result (%s)', async (otherFocused) => {
  renderHook(() => useCognitionBus(true));
  let closed!: ReturnType<typeof materialize>;
  act(() => {
    closed = materialize('a.ts');
    store.closeWorkspace(closed.id);
    finishRetraction(closed.id);
    if (otherFocused) { const other = materialize('b.ts'); store.focusWorkspace(other.id); }
    publishCognition({ type: 'verify', source: 'test-fixture', data: {
      verdict: 'pass', target: 'a.ts', output: 'A check output',
    } });
  });
  expect(store.getTabStoreSnapshot().recoverableTabs?.[0].content)
    .toMatchObject({ filepath: 'a.ts', verifyVerdict: 'pass', verifyOutput: 'A check output' });
  expect(store.getTabStoreSnapshot().tabs.every((tab) => tab.content?.verifyOutput !== 'A check output')).toBe(true);
});

it.each(['missing.ts', 'same.ts'])('does not guess a verification recipient for an unmatched or ambiguous target (%s)', (target) => {
  renderHook(() => useCognitionBus(true));
  act(() => {
    const closed = materialize('one/same.ts');
    store.closeWorkspace(closed.id);
    finishRetraction(closed.id);
    const other = materialize('two/same.ts');
    store.focusWorkspace(other.id);
    publishCognition({ type: 'verify', source: 'test-fixture', data: {
      verdict: 'pass', target, output: 'Uncorrelated check output',
    } });
  });
  const snapshot = store.getTabStoreSnapshot();
  expect([...snapshot.tabs, ...(snapshot.recoverableTabs ?? [])].every((tab) =>
    tab.content?.verifyOutput === 'Reported failure')).toBe(true);
});

it.each(['one/same.ts', 'one\\same.ts'])('rejects an explicit conflicting path after the matching result was forgotten (%s)', (target) => {
  renderHook(() => useCognitionBus(true));
  act(() => {
    const forgotten = materialize('one/same.ts');
    store.closeWorkspace(forgotten.id);
    finishRetraction(forgotten.id);
    store.forgetRecoverableMaterializedTab(forgotten.id);
    materialize('two/same.ts');
    publishCognition({ type: 'verify', source: 'test-fixture', data: {
      verdict: 'pass', target, output: 'Wrong result check',
    } });
  });
  expect(store.getTabStoreSnapshot().tabs[0].content)
    .toMatchObject({ filepath: 'two/same.ts', verifyVerdict: 'fail', verifyOutput: 'Reported failure' });
});

it.each(['same.ts', 'training_ground/same.ts'])('accepts a unique basename-only result when no conflicting path is known (%s)', (target) => {
  renderHook(() => useCognitionBus(true));
  act(() => {
    materialize('same.ts');
    publishCognition({ type: 'verify', source: 'test-fixture', data: {
      verdict: 'pass', target, output: 'Matching check',
    } });
  });
  expect(store.getTabStoreSnapshot().tabs[0].content)
    .toMatchObject({ filepath: 'same.ts', verifyVerdict: 'pass', verifyOutput: 'Matching check' });
});

it('keeps recovery reachable when context loss removes the renderer before closing geometry retires', async () => {
  await act(async () => { render(<LivingWorkspaceShell experienceMode="expert" />); });
  act(() => {
    for (let seat = 0; seat < 12; seat++) {
      const tab = store.showContentSurface({ filepath: `saved-${seat}.ts`, code: 'saved content', language: 'typescript' }, { seatIndex: seat });
      store.closeWorkspace(tab.id);
    }
  });
  expect(store.getTabStoreSnapshot().tabs).toHaveLength(12);
  act(() => setRendererFallbackPresentation(true));
  recent();
  expect(screen.getByRole('button', { name: 'Reopen saved-0.ts' })).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Reopen saved-0.ts' }));
  expect(screen.getByRole('heading', { name: 'saved-0.ts' })).toBeVisible();
  expect(store.getTabStoreSnapshot().recoverableTabs).toHaveLength(11);
});
