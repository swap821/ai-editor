import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FixtureJourneyPage from './FixtureJourneyPage';
import { createFixtureJourneyTransport } from './fixtureJourneyTransport';
import { installFixtureJourney } from './installFixtureJourney';
import { __resetAiosAdapterForTests, getPendingApproval } from '../../superbrain/lib/aiosAdapter';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { __resetTabStoreForTests, finishMaterializedTabRetraction, getTabStoreSnapshot } from '../../superbrain/lib/tabStore';
import { setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { EXPERIENCE_MODE_STORAGE_KEY } from '../experienceMode';
import { readFileSync } from 'node:fs';

// Only the WebGL root is substituted. Composer, real SSE/session/mirror
// admission, permission/receipt, store and reader/recovery owners stay real.
// The explicit retirement callback below stands in for GPU animation finish;
// no native motion or device acceptance is claimed by this DOM test.
vi.mock('@/components/canvas/WorkspaceCanvas', () => ({ default: () => <div className="scene-layer"><canvas aria-hidden="true" /></div> }));
let fixture: ReturnType<typeof createFixtureJourneyTransport>;
const previousMode = localStorage.getItem(EXPERIENCE_MODE_STORAGE_KEY);
afterEach(() => {
  cleanup(); fixture?.dispose(); __resetAiosAdapterForTests(); __resetTabStoreForTests();
  document.querySelectorAll('style[data-fixture-journey-test]').forEach((style) => style.remove());
  useMirrorStore.setState(useMirrorStore.getInitialState(), true); setConversationPhase('idle');
  vi.unstubAllGlobals();
  if (previousMode === null) localStorage.removeItem(EXPERIENCE_MODE_STORAGE_KEY);
  else localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, previousMode);
});
async function mount(reduced = false, isolate = false) {
  __resetAiosAdapterForTests(); __resetTabStoreForTests(); setConversationPhase('idle');
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, 'beginner');
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({ matches: reduced && query.includes('reduced-motion'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() })));
  if (isolate) {
    // Capture every replaced global so the one-way installer is isolated to
    // this test's page, not restored during an actual app remount.
    for (const name of ['fetch', 'EventSource', 'WebSocket', 'XMLHttpRequest']) {
      vi.stubGlobal(name, Reflect.get(window, name));
    }
    vi.stubGlobal('fetch', vi.fn<typeof fetch>());
    vi.stubGlobal('SpeechRecognition', vi.fn(() => { throw new Error('Native recognition must not be offered'); }));
    vi.stubGlobal('webkitSpeechRecognition', window.SpeechRecognition);
    vi.stubGlobal('navigator', { language: 'en', languages: ['en'], userAgent: navigator.userAgent, sendBeacon: vi.fn(), mediaDevices: { getUserMedia: vi.fn() } });
    fixture = installFixtureJourney(window);
  } else fixture = createFixtureJourneyTransport({ origin: window.location.origin, assetFetch: vi.fn<typeof fetch>() });
  vi.stubGlobal('fetch', fixture.fetch); vi.stubGlobal('EventSource', fixture.EventSource);
  const style = document.createElement('style'); style.dataset.fixtureJourneyTest = 'true';
  // Read the real styles rather than Vitest's disabled CSS-import stub.
  style.textContent = readFileSync('src/workbench/GagosChrome.css', 'utf8')
    + readFileSync('src/livingMirror/livingMirror.css', 'utf8'); document.head.append(style);
  render(<StrictMode><FixtureJourneyPage fixture={fixture} /></StrictMode>);
  await waitFor(() => expect(useMirrorStore.getState().projection).toBe('fresh'));
  expect(screen.getByText('Fixture—not backend work')).toBeVisible();
}
async function advance() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Advance fixture' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Advance fixture' }));
  await act(async () => {});
}
async function start(previewSelected = true) {
  fireEvent.change(screen.getByRole('textbox', { name: 'Talk to GAGOS' }), { target: { value: 'Create a greeting example' } });
  fireEvent.click(screen.getByRole('button', { name: /^Send$/ }));
  await waitFor(() => expect(fixture.getSnapshot().label).toBe('Advance to partial work'));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'working');
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-phase', 'acting');
  await advance();
  if (previewSelected) await screen.findByText('# Fixture preview — no file has been written');
  else await waitFor(() => expect(getTabStoreSnapshot().tabs.some((tab) =>
    tab.content?.code.trim() === '# Fixture preview — no file has been written')).toBe(true));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'working');
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-phase', 'acting');
  expect(document.querySelector('.lm-app')).not.toHaveAttribute('data-being-motion', 'verify');
  await advance();
  await screen.findByRole('alertdialog');
  expect(getPendingApproval()?.token).toMatch(/^fixture-/);
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'needs-permission');
  const chrome = document.querySelector('.gagos-chrome')!;
  const workspace = document.querySelector('.lm-surface')!;
  expect(getComputedStyle(document.querySelector('.lm-shell')!).zIndex).toBe('auto');
  expect(Number(getComputedStyle(chrome).zIndex)).toBeGreaterThan(Number(getComputedStyle(workspace).zIndex || 30));
  expect(Number(getComputedStyle(screen.getByRole('alertdialog')).zIndex)).toBeGreaterThan(20);
  const header = document.querySelector('.lm-header')!;
  expect(Number(getComputedStyle(header).zIndex)).toBeGreaterThan(Number(getComputedStyle(chrome).zIndex));
}
it('keeps opened Stop details above the real composer outside a permission request', async () => {
  await mount();
  const details = screen.getByRole('button', { name: 'Inspect emergency stop' });
  fireEvent.click(details);
  await screen.findByRole('region', { name: 'Stop state and outcomes' });
  const shell = document.querySelector('.lm-shell')!;
  expect(getComputedStyle(shell).zIndex).toBe('auto');
  expect(Number(getComputedStyle(document.querySelector('.lm-header')!).zIndex))
    .toBeGreaterThan(Number(getComputedStyle(document.querySelector('.gagos-chrome')!).zIndex));
  fireEvent.click(screen.getByRole('button', { name: 'Close details' }));
  expect(getComputedStyle(shell).zIndex).toBe('30');
  await waitFor(() => expect(details).toHaveFocus());
});

it.each([false, true])('keeps partial work, real Allow, Close and Reopen usable (reduced=%s)', async (reduced) => {
  await mount(reduced); await start();
  const tab = getTabStoreSnapshot().tabs.find((record) => record.kind === 'content')!;
  const reader = await screen.findByText('# Fixture preview — no file has been written');
  const scrollOwner = reader.closest('.lm-surface__body')!;
  scrollOwner.scrollTop = 21; fireEvent.scroll(scrollOwner);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-phase', 'awaiting-response'));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'waiting-response');
  expect(screen.getByRole('status', { name: 'GAGOS organism status' })).toHaveTextContent('GAGOS is waiting for the replay response; completion is unconfirmed.');
  expect(document.querySelector('.lm-being-status')).toHaveTextContent('GAGOS is waiting for the replay response; completion is unconfirmed.');
  expect(screen.queryByText('GAGOS is resting.')).not.toBeInTheDocument();
  expect(screen.getByText(/permission submitted.*waiting for the replay response/i)).toBeVisible();
  expect(screen.getByText('# Fixture preview — no file has been written')).toBe(reader);
  expect(scrollOwner.scrollTop).toBe(21);
  await advance();
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-phase', 'acting'));
  expect(screen.queryByText('GAGOS is waiting for the replay response; completion is unconfirmed.')).not.toBeInTheDocument();
  await advance(); await advance();
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'done-unverified'));
  expect(document.querySelector('.gagos-chrome')).toHaveAttribute('data-approval-pending', 'false');
  expect(screen.getByText('print("Hello from the fixture")')).toBe(reader);
  expect(scrollOwner.scrollTop).toBe(21);
  expect(getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.content?.streaming).toBe(false);
  // GPU driver only: the development control requests loss, and the real
  // context-loss listener/fallback bridge remains responsible for the UI.
  const canvas = document.querySelector('canvas')!;
  vi.spyOn(canvas, 'getContext').mockReturnValue({ getExtension: () => ({ loseContext: () => {
    canvas.dispatchEvent(new Event('webglcontextlost', { cancelable: true }));
  } }) } as unknown as WebGL2RenderingContext);
  fireEvent.click(screen.getByRole('button', { name: 'Simulate visual loss' }));
  await screen.findByTestId('renderer-fallback-notice');
  expect(screen.getByText('print("Hello from the fixture")')).toBe(reader);
  expect(scrollOwner.scrollTop).toBe(21);
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  act(() => { finishMaterializedTabRetraction(tab.id, getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.retractionToken); });
  expect(getTabStoreSnapshot().tabs.some((record) => record.id === tab.id)).toBe(false);
  fireEvent.click(within(screen.getByRole('main', { name: 'GAGOS conversation' })).getByRole('button', { name: /^Recent activity$/ }));
  fireEvent.click(await screen.findByRole('button', { name: 'Reopen fixture/hello.py' }));
  const reopened = await screen.findByText('print("Hello from the fixture")');
  expect(reopened).toBeVisible();
  expect(reopened.closest('.lm-surface__body')!.scrollTop).toBe(21);
  expect(getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.content?.code).toBe('print("Hello from the fixture")\n');
  expect(fixture.getSnapshot().pending).toBe(false);
}, 15000);
it('keeps Deny on the actual permission owner and exposes a declined partial reader', async () => {
  await mount(); await start();
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: "Don't allow" }));
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'refused'));
  expect(screen.getByText('# Fixture preview — no file has been written')).toBeVisible();
  expect(fixture.getSnapshot().label).toMatch(/no file was written/i);
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  expect(document.querySelector('.gagos-chrome')).toHaveAttribute('data-approval-pending', 'false');
});
it('releases a held decision when the actual composer supersedes its turn', async () => {
  await mount(); await start();
  const oldToken = getPendingApproval()!.token;
  fireEvent.change(screen.getByRole('textbox', { name: 'Talk to GAGOS' }), { target: { value: 'Create a newer greeting example' } });
  fireEvent.click(screen.getByRole('button', { name: /^Send$/ }));
  await advance(); await advance();
  await waitFor(() => expect(getPendingApproval()?.token).toBeTruthy());
  expect(getPendingApproval()!.token).not.toBe(oldToken);
  expect(fixture.getSnapshot().waitingForDecision).toBe(true);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: "Don't allow" }));
  await waitFor(() => expect(fixture.getSnapshot().waitingForDecision).toBe(false));
});
it('keeps a synthetic matching verification on the actual replay receipt', async () => {
  await mount(); act(() => fixture.setOutcome('verified')); await start();
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await advance(); await advance(); await advance(); await advance();
  await screen.findByRole('status', { name: 'Done' });
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'done-verified');
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.kind === 'content')?.content?.verifyEventId)
    .toBe(useMirrorStore.getState().lastVerificationEventId);
  expect(screen.getByText('Fixture—not backend work')).toBeVisible();
  fireEvent.click(screen.getByText('Reported check output'));
  expect(screen.getByText('Fixture observation only; not an executed check.')).toBeVisible();
}, 15000);
it.each([false, true])('keeps a repeated same-path check unattributed across body and receipt (closed=%s)', async (closed) => {
  await mount(); act(() => fixture.setOutcome('verified')); await start();
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await advance(); await advance(); await advance(); await advance();
  await screen.findByRole('status', { name: 'Done' });
  const previous = getTabStoreSnapshot().tabs.find((tab) => tab.kind === 'content')!;
  if (closed) {
    fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
    act(() => finishMaterializedTabRetraction(previous.id, getTabStoreSnapshot().tabs.find((tab) => tab.id === previous.id)?.retractionToken));
    expect(getTabStoreSnapshot().tabs.some((tab) => tab.id === previous.id)).toBe(false);
  }
  await start(closed);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await advance(); await advance(); await advance();
  expect(screen.getByText('Check not attributed')).toHaveClass('gagos-verify-toast--unknown');
  expect(screen.queryByText('Verified')).not.toBeInTheDocument();
  await advance();
  await screen.findByRole('status', { name: 'Finished, but not verified' });
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'done-unverified'));
  const snapshot = getTabStoreSnapshot();
  const versions = [...new Map([...snapshot.tabs, ...(snapshot.recoverableTabs ?? [])]
    .filter((tab) => tab.kind === 'content').map((tab) => [tab.id, tab])).values()];
  expect(versions).toHaveLength(2);
  expect(versions.find((tab) => tab.id === previous.id)?.content?.verifyVerdict).toBe('pass');
  expect(versions.find((tab) => tab.id !== previous.id)?.content?.verifyVerdict).toBeUndefined();
  expect(versions.find((tab) => tab.id !== previous.id)?.content?.verifyEventId).toBeUndefined();
  if (closed) {
    fireEvent.click(within(screen.getByRole('main', { name: 'GAGOS conversation' })).getByRole('button', { name: /^Recent activity$/ }));
    fireEvent.click(await screen.findByRole('button', { name: 'Forget fixture/hello.py' }));
    fireEvent.click(screen.getByRole('button', { name: 'Forget permanently' }));
    expect(getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
    expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'done-unverified');
    expect(screen.getByRole('status', { name: 'Finished, but not verified' })).toBeVisible();
  }
  expect(screen.getByText('Fixture—not backend work')).toBeVisible();
}, 15000);
it('reports a matching failed observation without losing partial work or claiming completion', async () => {
  await mount(); act(() => fixture.setOutcome('failed')); await start();
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await advance(); await advance(); await advance(); await advance();
  const receipt = await screen.findByRole('status', { name: 'That did not work.' });
  await waitFor(() => expect(within(receipt).getByText('The request did not complete. A reported check failed.')).toBeVisible());
  expect(screen.getByText('print("Hello from the fixture")')).toBeVisible();
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'failed');
}, 15000);
it('does not offer a crashing browser recognition route after the actual installer', async () => {
  await mount(false, true);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  expect(screen.queryByText(/Use browser recognition/)).not.toBeInTheDocument();
  expect(window.SpeechRecognition).toBeUndefined();
  expect(window.webkitSpeechRecognition).toBeUndefined();
  const composer = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(composer, { target: { value: 'Typing remains available' } });
  expect(composer).toHaveValue('Typing remains available');
  expect(screen.getByRole('button', { name: /^Send$/ })).toBeEnabled();
});
