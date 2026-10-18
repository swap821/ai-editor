import { StrictMode } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FixtureJourneyPage from './FixtureJourneyPage';
import SuperbrainApp from '../../superbrain/SuperbrainApp';
import { createFixtureJourneyTransport } from './fixtureJourneyTransport';
import { installFixtureJourney } from './installFixtureJourney';
import { __resetAiosAdapterForTests, getPendingApproval } from '../../superbrain/lib/aiosAdapter';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { __resetTabStoreForTests, closeWorkspace, finishMaterializedTabRetraction, focusWorkspace, getTabStoreSnapshot, openWorkspacePanel, showContentSurface, updateMaterializedTab } from '../../superbrain/lib/tabStore';
import { setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { setAmbientMotionPaused } from '../../superbrain/lib/reducedMotion';
import { EXPERIENCE_MODE_STORAGE_KEY } from '../experienceMode';
import { readFileSync } from 'node:fs';

// Only the WebGL root is substituted. Composer, real SSE/session/mirror
// admission, permission/receipt, store and reader/recovery owners stay real.
// The explicit retirement callback below stands in for GPU animation finish;
// no native motion or device acceptance is claimed by this DOM test.
vi.mock('@/components/canvas/WorkspaceCanvas', () => ({ default: () => <div className="scene-layer"><canvas aria-hidden="true" /></div> }));
let fixture: ReturnType<typeof createFixtureJourneyTransport>;
const previousMode = localStorage.getItem(EXPERIENCE_MODE_STORAGE_KEY);
const previousUrl = window.location.href;
const responsiveStyleCleanups: Array<() => void> = [];
afterEach(() => {
  cleanup(); fixture?.dispose(); __resetAiosAdapterForTests(); __resetTabStoreForTests();
  responsiveStyleCleanups.splice(0).forEach(dispose => dispose());
  document.querySelectorAll('style[data-fixture-journey-test]').forEach((style) => style.remove());
  useMirrorStore.setState(useMirrorStore.getInitialState(), true); setConversationPhase('idle');
  setAmbientMotionPaused(false);
  vi.unstubAllGlobals(); vi.unstubAllEnvs();
  window.history.replaceState(null, '', previousUrl);
  if (previousMode === null) localStorage.removeItem(EXPERIENCE_MODE_STORAGE_KEY);
  else localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, previousMode);
});
async function mount(reduced = false, isolate = false, narrow = false, responsiveMedia?: typeof window.matchMedia, officialEntry = false) {
  __resetAiosAdapterForTests(); __resetTabStoreForTests(); setConversationPhase('idle');
  useMirrorStore.setState(useMirrorStore.getInitialState(), true);
  localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, 'beginner');
  vi.stubGlobal('matchMedia', responsiveMedia ?? vi.fn((query: string) => ({ matches: (reduced && query.includes('reduced-motion')) || (narrow && query === '(max-width: 767px)'), media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() })));
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
    + readFileSync('src/livingMirror/livingMirror.css', 'utf8')
    + readFileSync('src/livingMirror/compactWorkingChrome.css', 'utf8'); document.head.append(style);
  // jsdom does not apply viewport media queries, but30.1.2 correctly refuses
  // focus on display:none ancestors. Apply the ACTUAL compact CSS rules for
  // the same mocked media owner; never focus a desktop-hidden phone control.
  // This supplies focus/visibility fidelity, not native layout/device proof.
  const compactCss = [...(style.sheet?.cssRules ?? [])]
    .filter((rule): rule is CSSMediaRule => rule.type === CSSRule.MEDIA_RULE
      && (rule as CSSMediaRule).conditionText === '(max-width: 767px)')
    .flatMap(rule => [...rule.cssRules].map(child => child.cssText)).join('\n');
  const compactStyle = document.createElement('style'); compactStyle.dataset.fixtureJourneyTest = 'true';
  const compactMedia = window.matchMedia('(max-width: 767px)');
  const syncCompactStyle = () => { compactStyle.textContent = compactMedia.matches ? compactCss : ''; };
  compactMedia.addEventListener('change', syncCompactStyle);
  responsiveStyleCleanups.push(() => compactMedia.removeEventListener('change', syncCompactStyle));
  syncCompactStyle(); document.head.append(compactStyle);
  render(<StrictMode>{officialEntry ? <SuperbrainApp /> : <FixtureJourneyPage fixture={fixture} />}</StrictMode>);
  await waitFor(() => expect(useMirrorStore.getState().projection).toBe('fresh'));
  if (!officialEntry) expect(screen.getByText('Fixture—not backend work')).toBeVisible();
}
async function advance() {
  // This is the fixture's transport control, not a product action. Scope the
  // accessible query to its real labeled owner instead of naming every hidden
  // Expert control in the app for each wait/click. Keep normal visibility checks.
  const controls = within(screen.getByRole('complementary', { name: 'Isolated development journey' }));
  await waitFor(() => expect(controls.getByRole('button', { name: 'Advance fixture' })).toBeEnabled());
  fireEvent.click(controls.getByRole('button', { name: 'Advance fixture' }));
  await act(async () => {});
}
// Development observation only: actual mirror admission, DOM/body projection,
// request owner and work retention stay real. No Stop/Clear command is granted.
it.each([false, true])('admits an observed Stop fixture and keeps new input/work until explicit post-clear send; reduced=%s', async reduced => {
  await mount(reduced);
  const input = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Create a greeting example' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await advance();
  const reader = await screen.findByText('# Fixture preview — no file has been written');
  const first = getTabStoreSnapshot().tabs.find(tab => tab.kind === 'content')!;
  fireEvent.change(input, { target: { value: 'Create the next draft only after explicit send' } });
  fireEvent.click(screen.getByRole('button', { name: 'Simulate observed Stop' }));
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-phase', 'stopped'));
  await waitFor(() => expect(fixture.getSnapshot().pending).toBe(false));
  expect(input).toBeEnabled();
  expect(input).toHaveValue('Create the next draft only after explicit send');
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByText(/new requests cannot be sent/i)).toBeVisible();
  expect(screen.getByText('# Fixture preview — no file has been written')).toBe(reader);
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === first.id)?.content).toMatchObject({ streaming: false, completion: 'cancelled' });
  expect(getPendingApproval()).toBeNull();
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(input).toHaveValue('Create the next draft only after explicit send');
  expect(fixture.getSnapshot().pending).toBe(false);
  expect(getTabStoreSnapshot().tabs.filter(tab => tab.kind === 'content')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', { name: 'Simulate observed Clear' }));
  await waitFor(() => expect(document.querySelector('.lm-app')).not.toHaveAttribute('data-being-phase', 'stopped'));
  expect(fixture.getSnapshot().pending).toBe(false);
  expect(input).toHaveValue('Create the next draft only after explicit send');
  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  expect(screen.getByText('# Fixture preview — no file has been written')).toBe(reader);
  fireEvent.click(screen.getByRole('button', { name: 'Send' }));
  await waitFor(() => expect(fixture.getSnapshot().pending).toBe(true));
  expect(input).toHaveValue('');
  expect(screen.getByText('Fixture—not backend work')).toBeVisible();
});
it.each(['close', 'escape', 'external'] as const)('returns Guided workspace %s to the real intake without changing the draft or running work', async (dismissal) => {
  await mount(false, false, true);
  const intake = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(intake, { target: { value: 'Keep this draft unsent.' } });
  intake.setSelectionRange(3, 16);
  let firstId = '';
  act(() => {
    firstId = showContentSurface({ filepath: 'first.py', code: 'first saved work', language: 'python' }, { seatIndex: 0 }).id;
    showContentSurface({ filepath: 'second.py', code: 'second saved work', language: 'python' }, { seatIndex: 1 });
    focusWorkspace(firstId);
  });
  const chooser = screen.getByRole('combobox', { name: 'Choose workspace' });
  chooser.focus();
  fireEvent.change(chooser, { target: { value: firstId } });
  const navigation = screen.getByRole('navigation', { hidden: true });
  // Guided navigation is now progressively available in More, not a
  // permanently CSS-hidden sibling. It must stay hidden while More is closed.
  expect(navigation.closest<HTMLDetailsElement>('.lm-compact-more')!.open).toBe(false);
  expect(navigation).not.toBeVisible();
  if (dismissal === 'close') fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  else if (dismissal === 'escape') fireEvent.keyDown(screen.getByRole('heading', { name: 'first.py' }), { key: 'Escape' });
  else act(() => closeWorkspace(firstId));
  expect(intake).toHaveFocus();
  expect(intake).toHaveValue('Keep this draft unsent.');
  expect([intake.selectionStart, intake.selectionEnd]).toEqual([3, 16]);
  expect(screen.queryByRole('region', { name: 'Selected workspace' })).not.toBeInTheDocument();
  expect(getTabStoreSnapshot().recoverableTabs?.some((tab) => tab.id === firstId)).toBe(true);
  expect(fixture.getSnapshot().pending).toBe(false);
  expect(fixture.getSnapshot().label).toBe('Type an example request in the real composer.');
});

it('does not move focus or lose oversized Guided work when Close cannot retain it', async () => {
  await mount(false, false, true);
  act(() => {
    const tab = showContentSurface({ filepath: 'large.py', code: 'x'.repeat(3 * 1024 * 1024), language: 'python' }, { seatIndex: 0 });
    focusWorkspace(tab.id);
  });
  const close = screen.getByRole('button', { name: 'Close workspace' });
  close.focus();
  fireEvent.click(close);
  expect(close).toHaveFocus();
  expect(screen.getByRole('region', { name: 'Selected workspace' })).toBeVisible();
  expect(screen.getByRole('status', { name: 'Result recovery' })).toHaveTextContent('remains open');
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.kind === 'content')?.content?.code.length).toBe(3 * 1024 * 1024);
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).not.toHaveFocus();
});
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
it.each([false, true])('keeps explicit Conversation through admitted permission/replay/stream/outcome (reduced=%s)', async (reduced) => {
  await mount(reduced); await start();
  const tab = getTabStoreSnapshot().tabs.find((record) => record.kind === 'content')!;
  const mode = (name: 'Guided' | 'Expert / Mirror') => within(screen.getByRole('group', { name: 'Experience mode' })).getByRole('button', { name });
  fireEvent.click(mode('Expert / Mirror'));
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' })).getByRole('button', { name: 'Conversation' }));
  const intake = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(intake, { target: { value: 'Keep this next draft unsent.' } });
  intake.setSelectionRange(5, 14);
  expect(getTabStoreSnapshot().focusId).toBeNull();
  const heldApproval = getPendingApproval();
  fireEvent.click(mode('Guided'));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-working', 'false');
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'needs-permission');
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getPendingApproval()).toBe(heldApproval);
  expect(screen.getByText('Holding for your approval before I build that.')).toBeVisible();
  expect(screen.queryByRole('region', { name: 'Selected workspace' })).not.toBeInTheDocument();
  expect(intake).toHaveValue('Keep this next draft unsent.');
  expect([intake.selectionStart, intake.selectionEnd]).toEqual([5, 14]);
  fireEvent.click(mode('Expert / Mirror'));
  // A held decision stays accessible despite leaving its work reader.
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'AUTHORIZE' }));
  await advance(); await advance(); await advance();
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'done-unverified'));
  expect(getTabStoreSnapshot().focusId).toBeNull();
  expect(getTabStoreSnapshot().attention).toBeNull();
  expect(screen.queryByRole('region', { name: 'Selected workspace' })).not.toBeInTheDocument();
  expect(intake).toHaveValue('Keep this next draft unsent.');
  expect([intake.selectionStart, intake.selectionEnd]).toEqual([5, 14]);
  const completed = getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)!;
  expect(completed.content).toMatchObject({ code: 'print("Hello from the fixture")\n', filepath: 'fixture/hello.py', streaming: false });
  expect(getTabStoreSnapshot().tabs.filter((record) => record.kind === 'content')).toHaveLength(1);
  fireEvent.click(mode('Guided'));
  fireEvent.click(within(screen.getByRole('region', { name: 'Conversation' })).getByRole('button', { name: 'Review' }));
  expect(getTabStoreSnapshot().focusId).toBe(tab.id);
  expect(screen.getByText('print("Hello from the fixture")')).toBeVisible();
  expect(intake).toHaveValue('Keep this next draft unsent.');
});

it('reveals a keyboard-focused accessory horizontally without changing draft, vertical scroll or starting work', async () => {
  await mount(false, false, true);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  const intake = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(intake, { target: { value: 'Keep this accessory-focus draft unsent.' } });
  intake.setSelectionRange(5, 14);
  const model = screen.getByRole('button', { name: /^Chat model:/ });
  const swarm = screen.getByRole('button', { name: /^Swarm mode off/ });
  const accessories = model.closest<HTMLElement>('.gagos-bar__accessories')!;
  // jsdom has no layout: substitute only browser measurements, while the
  // actual composer/focus handler, draft, owners and transport remain real.
  vi.spyOn(accessories, 'getBoundingClientRect').mockReturnValue(new DOMRect(100, 20, 110, 56));
  Object.defineProperties(accessories, { clientWidth: { configurable: true, value: 110 }, scrollWidth: { configurable: true, value: 180 } });
  vi.spyOn(swarm, 'getBoundingClientRect').mockReturnValue(new DOMRect(192, 22, 48, 44));
  const modelBounds = vi.spyOn(model, 'getBoundingClientRect').mockReturnValue(new DOMRect(88, 22, 44, 44));
  accessories.scrollLeft = 12; accessories.scrollTop = 7;
  act(() => swarm.focus());
  expect(swarm).toHaveFocus();
  expect(accessories.scrollLeft).toBe(42);
  act(() => model.focus());
  expect(accessories.scrollLeft).toBe(30);
  modelBounds.mockReturnValue(new DOMRect(132, 22, 44, 44));
  act(() => intake.focus()); act(() => model.focus());
  expect(accessories.scrollLeft).toBe(30);
  expect(accessories.scrollTop).toBe(7);
  expect(intake).toHaveValue('Keep this accessory-focus draft unsent.');
  expect([intake.selectionStart, intake.selectionEnd]).toEqual([5, 14]);
  expect(fixture.getSnapshot().pending).toBe(false);
  expect(getPendingApproval()).toBeNull();
});

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
  const scrollOwner = reader.closest<HTMLElement>('.lm-surface__body')!;
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
  const receipt = within(scrollOwner).getByRole('status', { name: 'Finished, but not verified' });
  fireEvent.click(within(receipt).getByLabelText('Receipt details: Finished, but not verified'));
  await waitFor(() => expect(within(receipt).getByRole('button', { name: 'Run a check' })).toBeVisible());
  expect(within(receipt).getByRole('button', { name: 'Run a check' })).toBeVisible();
  expect(screen.getAllByRole('status', { name: 'Finished, but not verified' })).toHaveLength(1);
  fireEvent.click(within(receipt).getByRole('button', { name: 'Run a check' }));
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toHaveFocus();
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toHaveValue('Run a check for fixture/hello.py.');
  expect(fixture.getSnapshot().pending).toBe(false);
  expect(getPendingApproval()).toBeNull();
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
  expect(within(reopened.closest<HTMLElement>('.lm-surface__body')!).getByRole('status', { name: 'Finished, but not verified' })).toBeVisible();
  expect(getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.content?.code).toBe('print("Hello from the fixture")\n');
  expect(fixture.getSnapshot().pending).toBe(false);
}, 15000);
it('never attaches the current receipt to a different same-path artifact reader', async () => {
  await mount(); await start();
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Allow once' }));
  await advance(); await advance(); await advance();
  const own = getTabStoreSnapshot().tabs.find(tab => tab.kind === 'content')!;
  const receipt = screen.getByRole('status', { name: 'Finished, but not verified' });
  expect(receipt.closest<HTMLElement>('.lm-artifact-receipt-host')?.dataset.artifactId).toBe(own.id);
  let foreignId = '';
  act(() => {
    // The surface owner intentionally reuses an existing same-path surface.
    // Model a genuinely different generation, then admit its final path.
    foreignId = showContentSurface({ filepath: 'writing', code: 'Different same-path artifact', language: 'python' }).id;
    updateMaterializedTab(foreignId, { content: { filepath: 'fixture/hello.py', code: 'Different same-path artifact', language: 'python' } });
    focusWorkspace(foreignId);
  });
  expect(foreignId).not.toBe(own.id);
  const foreignReader = screen.getByText('Different same-path artifact').closest<HTMLElement>('.lm-surface__body')!;
  expect(foreignReader.querySelector('.gagos-receipt')).toBeNull();
  expect(screen.getByRole('status', { name: 'Finished, but not verified' }).closest('.gagos-chat__context')).not.toBeNull();
  expect(screen.getAllByRole('status', { name: 'Finished, but not verified' })).toHaveLength(1);
  act(() => focusWorkspace(own.id));
  expect(screen.getByRole('status', { name: 'Finished, but not verified' }).closest<HTMLElement>('.lm-artifact-receipt-host')?.dataset.artifactId).toBe(own.id);
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === foreignId)?.content?.code).toBe('Different same-path artifact');
  expect(fixture.getSnapshot().pending).toBe(false);
});

it('keeps Deny on the actual permission owner and exposes a declined partial reader', async () => {
  await mount();
  const appViewport = document.querySelector<HTMLElement>('.fixture-journey__app')!;
  // Native typing scrolls this short development frame before the decision.
  // A newly admitted critical request must expose Stop/body at its start.
  appViewport.scrollTop = 97;
  await start();
  expect(appViewport.scrollTop).toBe(0);
  const reader = screen.getByText('# Fixture preview — no file has been written');
  reader.closest('.lm-surface__body')!.scrollTop = 21;
  appViewport.scrollTop = 55;
  fireEvent.change(screen.getByRole('textbox', { name: 'Talk to GAGOS' }), { target: { value: 'Keep this unsent draft.' } });
  expect(appViewport.scrollTop).toBe(55);
  expect(reader.closest('.lm-surface__body')!.scrollTop).toBe(21);
  fireEvent.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: "Don't allow" }));
  await waitFor(() => expect(document.querySelector('.lm-app')).toHaveAttribute('data-being-task-state', 'refused'));
  expect(screen.getByText('# Fixture preview — no file has been written')).toBeVisible();
  expect(fixture.getSnapshot().label).toMatch(/no file was written/i);
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  expect(document.querySelector('.gagos-chrome')).toHaveAttribute('data-approval-pending', 'false');
  expect(screen.getByText('# Fixture preview — no file has been written')).toBe(reader);
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toHaveValue('Keep this unsent draft.');
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
it('opts into quieter working chrome without moving Stop, input or the result into More', async () => {
  window.history.replaceState(null, '', '?physical-gallery=journey');
  await mount(false, false, true);
  expect(document.querySelector('.lm-compact-more')).toBeNull(); // resting unchanged
  act(() => { showContentSurface({ filepath: 'prototype.py', code: 'retained prototype result', language: 'python' }, { seatIndex: 0 }); });
  const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more')!;
  await waitFor(() => expect(more.querySelector('.lm-navigation')).not.toBeNull());
  expect(more.open).toBe(false);
  expect(more.querySelector('.lm-connection__details')).not.toBeNull();
  expect(document.querySelectorAll('.lm-navigation')).toHaveLength(1);
  expect(document.querySelectorAll('.gagos-experience-switch')).toHaveLength(1);
  expect(more.querySelector('.lm-stop')).toBeNull();
  expect(more.querySelector('.gagos-input')).toBeNull();
  expect(more.querySelector('.lm-surface')).toBeNull();
  const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Keep this prototype draft' } });
  more.open = true; fireEvent(more, new Event('toggle'));
  fireEvent.click(within(more).getByRole('button', { name: 'Expert / Mirror' }));
  expect(input).toHaveValue('Keep this prototype draft');
  expect(screen.getByText('retained prototype result')).toBeVisible();
  fireEvent.keyDown(more, { key: 'Escape' });
  await waitFor(() => expect(more.open).toBe(false));
  expect(document.activeElement).toBe(more.querySelector('summary'));
  fireEvent.click(screen.getByRole('button', { name: 'Simulate observed Stop' }));
  await waitFor(() => expect(more.querySelector('summary')).toHaveAttribute('aria-disabled', 'true'));
  expect(input).toHaveValue('Keep this prototype draft');
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  expect(screen.getByText('retained prototype result')).toBeVisible();
});
it.each(['motion', 'workspace'] as const)('dismisses More after a portaled %s action without hiding focus or losing work', async (action) => {
  window.history.replaceState(null, '', '?physical-gallery=journey');
  await mount(false, false, true);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  let artifactId = '';
  act(() => { artifactId = showContentSurface({ filepath: 'menu.py', code: 'retained menu work', language: 'python' }, { seatIndex: 0 }).id; });
  const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more')!;
  await waitFor(() => expect(more.querySelector('.lm-navigation')).not.toBeNull());
  const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Keep this prototype menu draft' } });
  more.open = true; fireEvent(more, new Event('toggle'));
  more.querySelector<HTMLDetailsElement>('.lm-expert-mobile-surfaces')!.open = true;
  const taskGroup = [...more.querySelectorAll<HTMLDetailsElement>('.lm-expert-mobile-surface-group')]
    .find(group => group.querySelector('summary')?.textContent === 'Task')!;
  taskGroup.open = true;
  // matchMedia selects the real mobile owner, but jsdom does not apply the
  // phone CSS viewport. Native checks separately prove these controls paint.
  const button = within(more).getByRole('button', { name: action === 'motion' ? 'Pause ambient motion' : 'Recent observations', hidden: true });
  button.focus(); fireEvent.click(button);
  await waitFor(() => expect(more.open).toBe(false));
  if (action === 'motion') expect(document.activeElement).toBe(more.querySelector('summary'));
  else await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Recent observations', level: 2 })));
  // A closed details still paints its summary. Only its hidden content must
  // release focus; treating that visible summary as hidden is a false oracle.
  expect(more.querySelector('.lm-compact-more__content')!.contains(document.activeElement)).toBe(false);
  expect(input).toHaveValue('Keep this prototype menu draft');
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === artifactId)?.content?.code).toBe('retained menu work');
  expect(fixture.getSnapshot().pending).toBe(false);
  if (action === 'motion') {
    more.open = true; fireEvent(more, new Event('toggle'));
    fireEvent.click(within(more).getByRole('button', { name: 'Resume ambient motion', hidden: true }));
  }
});
it('retires hidden More focus on an admitted Stop without reopening or sending the draft on Clear', async () => {
  window.history.replaceState(null, '', '?physical-gallery=journey');
  await mount(false, false, true);
  act(() => { showContentSurface({ filepath: 'held-menu.py', code: 'retained through Stop', language: 'python' }, { seatIndex: 0 }); });
  const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Keep my interrupted menu draft' } });
  const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more')!;
  more.open = true; fireEvent(more, new Event('toggle'));
  within(more).getByRole('button', { name: 'Expert / Mirror' }).focus();
  // A transport observation arrives without an outside pointer moving focus.
  act(() => fixture.observeStop(true));
  await waitFor(() => expect(more.querySelector('summary')).toHaveAttribute('aria-disabled', 'true'));
  expect(more.open).toBe(false);
  expect(document.activeElement).toBe(more.querySelector('summary'));
  expect(input).toHaveValue('Keep my interrupted menu draft');
  expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  act(() => fixture.observeStop(false));
  await waitFor(() => expect(more.querySelector('summary')).not.toHaveAttribute('aria-disabled'));
  expect(more.open).toBe(false);
  expect(input).toHaveValue('Keep my interrupted menu draft');
  expect(screen.getByText('retained through Stop')).toBeVisible();
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['diagnostics', 'closed-navigation', 'open-navigation'] as const)('routes Escape from %s through the real portaled controls', async (route) => {
  window.history.replaceState(null, '', '?physical-gallery=journey');
  await mount(false, false, true);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  act(() => { showContentSurface({ filepath: 'escape.py', code: 'retained Escape work', language: 'python' }, { seatIndex: 0 }); });
  const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more')!;
  await waitFor(() => expect(more.querySelector('.lm-navigation')).not.toBeNull());
  more.open = true; fireEvent(more, new Event('toggle'));
  const navigation = more.querySelector<HTMLDetailsElement>('.lm-expert-mobile-surfaces')!;
  navigation.open = route === 'open-navigation';
  const target = more.querySelector<HTMLElement>(route === 'diagnostics' ? '.lm-connection__details > summary' : '.lm-expert-mobile-surfaces > summary')!;
  target.focus(); fireEvent.keyDown(target, { key: 'Escape' });
  if (route === 'open-navigation') {
    expect(navigation.open).toBe(false);
    expect(more.open).toBe(true);
    expect(document.activeElement).toBe(target);
    fireEvent.keyDown(target, { key: 'Escape' });
  }
  await waitFor(() => expect(more.open).toBe(false));
  expect(document.activeElement).toBe(more.querySelector('summary'));
  expect(screen.getByText('retained Escape work')).toBeVisible();
  expect(fixture.getSnapshot().pending).toBe(false);
});

function responsiveCompactMedia(initialNarrow: boolean) {
  let narrow = initialNarrow;
  const listeners = new Map<string, Set<(event: MediaQueryListEvent) => void>>();
  const matches = (query: string) => (query === '(max-width: 767px)' || query === '(max-width: 360px)') && narrow;
  const matchMedia = vi.fn((media: string) => {
    const callbacks = listeners.get(media) ?? new Set(); listeners.set(media, callbacks);
    return { media, get matches() { return matches(media); }, onchange: null,
      addEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => callbacks.add(callback),
      removeEventListener: (_type: string, callback: (event: MediaQueryListEvent) => void) => callbacks.delete(callback),
      addListener: (callback: (event: MediaQueryListEvent) => void) => callbacks.add(callback),
      removeListener: (callback: (event: MediaQueryListEvent) => void) => callbacks.delete(callback),
      dispatchEvent: () => true,
    };
  }) as typeof window.matchMedia;
  const notify = (media: string) => {
    for (const callback of listeners.get(media) ?? []) callback({ media, matches: matches(media) } as MediaQueryListEvent);
  };
  return { matchMedia, setNarrow(nextNarrow: boolean) { narrow = nextNarrow; }, notify, resize(nextNarrow: boolean) {
    narrow = nextNarrow;
    for (const media of ['(max-width: 767px)', '(max-width: 360px)']) {
      notify(media);
    }
  } };
}
it.each(['beginner', 'expert'] as const)('uses compact working chrome at the official production entry in %s mode without a query flag', async (mode) => {
  vi.stubEnv('DEV', false);
  window.history.replaceState(null, '', '/');
  await mount(false, false, true, undefined, true);
  if (mode === 'expert') fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  const input = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Keep this official-entry draft' } });
  act(() => { showContentSurface({ filepath: 'official.py', code: 'official entry retained work', language: 'python' }, { seatIndex: 0 }); });
  const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more');
  expect(more).not.toBeNull();
  expect(document.querySelector('.lm-surface__body:not([hidden])')).not.toBeNull();
  expect(input).toHaveValue('Keep this official-entry draft');
  expect(screen.getByText('official entry retained work')).toBeVisible();
  expect(screen.getByRole('button', { name: 'Emergency stop' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled();
  more!.open = true; fireEvent(more!, new Event('toggle'));
  expect(within(more!).getByRole('button', { name: 'Expert / Mirror', hidden: true })).toBeInTheDocument();
  expect(more!.querySelector('.lm-navigation')).not.toBeNull();
  expect(more!.querySelector('.lm-connection__details')).not.toBeNull();
  expect(document.querySelectorAll('.lm-navigation')).toHaveLength(1);
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['desktop-work', 'phone-rest'] as const)('keeps the official %s composition outside compact working chrome', async (scenario) => {
  vi.stubEnv('DEV', false);
  window.history.replaceState(null, '', '/');
  await mount(false, false, scenario === 'phone-rest', undefined, true);
  if (scenario === 'desktop-work') act(() => { showContentSurface({ filepath: 'desktop.py', code: 'desktop work', language: 'python' }, { seatIndex: 0 }); });
  expect(document.querySelector('.lm-compact-more')).toBeNull();
  expect(screen.getByRole('textbox', { name: 'Talk to GAGOS' })).toBeEnabled();
  expect(screen.getByRole('button', { name: 'Emergency stop' })).toBeEnabled();
  expect(fixture.getSnapshot().pending).toBe(false);
});

type ResizeControl = 'guided' | 'expert' | 'focus' | 'diagnostics' | 'quality' | 'more';
function resizeControl(key: ResizeControl): HTMLElement {
  if (key === 'guided' || key === 'expert') return screen.getByRole('button', { name: key === 'guided' ? 'Guided' : 'Expert / Mirror', hidden: true });
  return document.querySelector<HTMLElement>(key === 'focus' ? '.gagos-focus-toggle'
    : key === 'diagnostics' ? '.lm-connection__details > summary'
      : key === 'quality' ? '.lm-rendering-preferences select' : '.lm-compact-more > summary')!;
}
async function mountResizableWorkingChrome(narrow: boolean) {
  window.history.replaceState(null, '', '?physical-gallery=journey');
  const media = responsiveCompactMedia(narrow);
  await mount(false, false, narrow, media.matchMedia);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  act(() => { showContentSurface({ filepath: 'resize.py', code: 'retained resize work', language: 'python' }, { seatIndex: 0 }); });
  const input = screen.getByRole<HTMLInputElement>('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'Keep this resize draft' } }); input.setSelectionRange(3, 12);
  if (narrow) {
    const more = document.querySelector<HTMLDetailsElement>('.lm-compact-more')!;
    more.open = true; fireEvent(more, new Event('toggle'));
  }
  const diagnostics = document.querySelector<HTMLDetailsElement>('.lm-connection__details')!;
  diagnostics.open = true; fireEvent(diagnostics, new Event('toggle'));
  return { media, input, reader: document.querySelector('.lm-surface__body:not([hidden])') };
}
it.each(['guided', 'expert', 'focus', 'diagnostics', 'quality', 'more'] as const)('keeps %s focus when the working phone prototype widens', async (key) => {
  const { media, input, reader } = await mountResizableWorkingChrome(true);
  resizeControl(key).focus();
  act(() => media.resize(false));
  await waitFor(() => expect(document.querySelector('.lm-compact-more')).toBeNull());
  // The desktop diagnostic summary is CSS-hidden. Its visible quality
  // control is the equivalent destination, not an unfocusable disclosure.
  const destination = resizeControl(key === 'more' ? 'expert' : key === 'diagnostics' ? 'quality' : key);
  await waitFor(() => expect(document.activeElement).toBe(destination));
  expect(destination).toBeVisible();
  expect(input).toHaveValue('Keep this resize draft');
  expect([input.selectionStart, input.selectionEnd]).toEqual([3, 12]);
  expect(document.querySelector('.lm-surface__body:not([hidden])')).toBe(reader);
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['guided', 'expert', 'focus', 'quality'] as const)('keeps %s reachable when desktop controls fold into closed More', async (key) => {
  const { media, input, reader } = await mountResizableWorkingChrome(false);
  resizeControl(key).focus();
  act(() => media.resize(true));
  await waitFor(() => expect(document.querySelector('.lm-compact-more')).not.toBeNull());
  await waitFor(() => expect(document.activeElement).toBe(resizeControl('more')));
  expect(document.querySelector<HTMLDetailsElement>('.lm-compact-more')!.open).toBe(false);
  expect(input).toHaveValue('Keep this resize draft');
  expect(document.querySelector('.lm-surface__body:not([hidden])')).toBe(reader);
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['input', 'reader'] as const)('does not steal an explicit %s focus handoff during prototype resize', async (destination) => {
  const { media, input, reader } = await mountResizableWorkingChrome(true);
  resizeControl('expert').focus();
  const target = destination === 'input' ? input : reader!.querySelector<HTMLElement>('pre')!;
  act(() => { media.resize(false); target.focus(); });
  await waitFor(() => expect(document.querySelector('.lm-compact-more')).toBeNull());
  expect(document.activeElement).toBe(target);
  expect(input).toHaveValue('Keep this resize draft');
});
it.each(['expert', 'quality'] as const)('keeps %s focus when the shell media event precedes the parent prototype event', async (key) => {
  const { media, input, reader } = await mountResizableWorkingChrome(false);
  resizeControl(key).focus();
  media.setNarrow(true);
  // Native media callbacks need not share a React batch. The shell can learn
  // about the compact width before the parent learns to mount the More slot.
  act(() => media.notify('(max-width: 360px)'));
  expect(document.activeElement).toBe(resizeControl(key));
  act(() => media.notify('(max-width: 767px)'));
  await waitFor(() => expect(document.activeElement).toBe(resizeControl('more')));
  expect(document.querySelector<HTMLDetailsElement>('.lm-compact-more')!.open).toBe(false);
  expect(input).toHaveValue('Keep this resize draft');
  expect(document.querySelector('.lm-surface__body:not([hidden])')).toBe(reader);
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['action', 'group'] as const)('keeps desktop navigation %s focus reachable when it folds into More', async (control) => {
  const { media, input, reader } = await mountResizableWorkingChrome(false);
  const navigation = document.querySelector<HTMLElement>('.lm-navigation')!;
  const target = control === 'action' ? within(navigation).getByRole('button', { name: 'Missions' })
    : within(navigation).getByText('Authority', { selector: 'summary' });
  target.focus();
  act(() => media.resize(true));
  await waitFor(() => expect(document.activeElement).toBe(resizeControl('more')));
  expect(document.querySelector<HTMLDetailsElement>('.lm-compact-more')!.open).toBe(false);
  expect(input).toHaveValue('Keep this resize draft');
  expect(document.querySelector('.lm-surface__body:not([hidden])')).toBe(reader);
  expect(fixture.getSnapshot().pending).toBe(false);
});
it('uses the existing Conversation entry for phone navigation focus on widening', async () => {
  const { media, input } = await mountResizableWorkingChrome(true);
  document.querySelector<HTMLElement>('.lm-expert-mobile-surfaces > summary')!.focus();
  act(() => media.resize(false));
  await waitFor(() => expect(document.activeElement).toBe(within(screen.getByRole('navigation')).getByRole('button', { name: 'Conversation' })));
  expect(input).toHaveValue('Keep this resize draft');
  expect(fixture.getSnapshot().pending).toBe(false);
});
it('recovers navigation focus when phone CSS hides its desktop group before the media callback', async () => {
  const { media, input } = await mountResizableWorkingChrome(false);
  const navigation = document.querySelector<HTMLElement>('.lm-navigation')!;
  const target = within(navigation).getByRole('button', { name: 'Project files' });
  target.focus();
  expect(document.activeElement).toBe(target);
  // Native CSS is applied before matchMedia callbacks. jsdom does not apply
  // viewport queries, so reproduce that observed focus-loss boundary directly.
  target.closest<HTMLElement>('.lm-expert-group')!.style.display = 'none';
  // jsdom does not automatically run browser focus fixup on CSS hiding, and
  // blur() now refuses an already non-focusable target. Use its public
  // viewport focus step to reproduce native BODY focus, not a focus mock.
  document.documentElement.focus();
  expect(document.activeElement).toBe(document.body);
  act(() => media.resize(true));
  await waitFor(() => expect(document.activeElement).toBe(resizeControl('more')));
  expect(input).toHaveValue('Keep this resize draft');
  expect(fixture.getSnapshot().pending).toBe(false);
});
it.each(['pointer', 'outside-pointer', 'outside-focus', 'window-blur'] as const)('does not restore deliberately abandoned navigation after %s', async (abandonment) => {
  const { media, input } = await mountResizableWorkingChrome(false);
  const navigation = document.querySelector<HTMLElement>('.lm-navigation')!;
  const target = within(navigation).getByRole('button', { name: 'Project files' });
  target.focus();
  if (abandonment === 'pointer') fireEvent.pointerDown(document.querySelector('.scene-layer')!);
  else if (abandonment === 'outside-pointer') fireEvent.pointerDown(screen.getByRole('button', { name: 'Simulate visual loss' }));
  else if (abandonment === 'outside-focus') { const outside = screen.getByRole('button', { name: 'Simulate visual loss' }); outside.focus(); outside.blur(); }
  else fireEvent(window, new Event('blur'));
  target.blur();
  target.closest<HTMLElement>('.lm-expert-group')!.style.display = 'none';
  act(() => media.resize(true));
  await waitFor(() => expect(document.querySelector('.lm-compact-more')).not.toBeNull());
  expect(document.activeElement).not.toBe(resizeControl('more'));
  expect(input).toHaveValue('Keep this resize draft');
  expect(fixture.getSnapshot().pending).toBe(false);
});
it('returns to resting chrome when Guided hides the selected Expert-only panel', async () => {
  await mountResizableWorkingChrome(true);
  act(() => openWorkspacePanel('settings', 'Settings'));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-working', 'true');
  fireEvent.click(screen.getByRole('button', { name: 'Guided' }));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-working', 'false');
  expect(document.querySelector('.lm-compact-more')).toBeNull();
  expect(getTabStoreSnapshot().panels?.some((panel) => panel.id === 'settings' && panel.open)).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: 'Expert / Mirror' }));
  expect(document.querySelector('.lm-app')).toHaveAttribute('data-working', 'true');
  expect(document.querySelector('.lm-compact-more')).not.toBeNull();
  expect(getTabStoreSnapshot().focusId).toBe('settings');
  await act(async () => {});
  expect(fixture.getSnapshot().pending).toBe(false);
});
