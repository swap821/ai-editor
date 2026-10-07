import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { __resetAiosAdapterForTests, approvePendingApproval, getPendingApproval, rejectPendingApproval } from '../superbrain/lib/aiosAdapter';
import { __resetTabStoreForTests, focusMaterializedTab, getTabStoreSnapshot, setMaterializedTabLifecycle, showContentSurface } from '../superbrain/lib/tabStore';
import { useMirrorStore } from '../superbrain/lib/mirrorStore';
import { setConversationPhase } from '../superbrain/lib/conversationPhaseBus';
import { beingFactsFromStores } from '../livingMirror/being/presentationFromStores';
import { EXPERIENCE_MODE_STORAGE_KEY, type ExperienceMode } from '../livingMirror/experienceMode';
import { publishCognition } from '../superbrain/lib/cognitionBus';

type Stream = { frame: (event: string, data?: object) => void; end: () => void; cancellations: () => number };
const streams = new Map<string, Stream>();
const initialMirror = useMirrorStore.getState();
let confirmedDecline = true;
let priorMode: string | null;

// Substitute only HTTP. Actual adapter/session/SSE, both approval panels,
// submission hook, receipts, stores and reading DOM remain real. No live
// backend execution, WebGL/device or human-acceptance evidence is claimed.
beforeEach(() => {
  streams.clear();
  confirmedDecline = true;
  priorMode = localStorage.getItem(EXPERIENCE_MODE_STORAGE_KEY);
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  setConversationPhase('idle');
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    addListener: vi.fn(), removeListener: vi.fn(), onchange: null, dispatchEvent: vi.fn(),
  })));
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/api/v1/auth/session')) {
      return new Response(JSON.stringify({ authenticated: true }), { headers: { 'Content-Type': 'application/json' } });
    }
    if (String(url).endsWith('/api/generate')) {
      const body = JSON.parse(String(init?.body));
      const prompt = body.messages[0].content[0].text;
      const token = body.approvalTokens[0] ?? (prompt === 'create next.py' ? 'next' : 'initial');
      if (prompt !== 'create gated_file.py' && prompt !== 'create next.py') throw new Error('Unexpected replay prompt');
      let closed = false;
      let cancellations = 0;
      const stream = new ReadableStream<Uint8Array>({ start(controller) {
        streams.set(token, {
          frame: (event, data = {}) => { if (!closed) controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)); },
          end: () => { if (!closed) { closed = true; controller.close(); } },
          cancellations: () => cancellations,
        });
      }, cancel() { closed = true; cancellations += 1; } });
      return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
    }
    if (String(url).endsWith('/api/v1/approval/req')) {
      const decision = JSON.parse(String(init?.body));
      if (decision.approve !== false || decision.approvalToken !== 'first-token') throw new Error('Wrong decline boundary');
      return new Response(JSON.stringify({ decision: confirmedDecline ? 'rejected' : 'unknown' }), { headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
  }));
});
afterEach(() => {
  cleanup();
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  useMirrorStore.setState(initialMirror);
  if (priorMode === null) localStorage.removeItem(EXPERIENCE_MODE_STORAGE_KEY);
  else localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, priorMode);
  vi.unstubAllGlobals();
});

function permission(token = 'first-token') {
  return { text: 'Permission to create the bounded file', input: {
    approvalToken: token, creations: [{ filepath: 'src/gated_file.py', content: 'print("proposal")' }],
  } };
}
async function stream(token: string) {
  await waitFor(() => expect(streams.has(token)).toBe(true));
  return streams.get(token)!;
}
async function heldWork(mode: ExperienceMode, closeInitial = true, initialEvent: 'code' | 'code_chunk' = 'code_chunk') {
  localStorage.setItem(EXPERIENCE_MODE_STORAGE_KEY, mode);
  const { default: GagosChrome } = await import('./GagosChrome');
  const { LivingWorkspaceShell } = await import('../livingMirror/LivingWorkspaceShell');
  render(<><GagosChrome integrated experienceMode={mode} /><LivingWorkspaceShell experienceMode={mode} /></>);
  const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'create gated_file.py' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  const initial = await stream('initial');
  await act(async () => {
    initial.frame(initialEvent, { code: 'print("partial")', language: 'python', filepath: 'src/gated_file.py' });
    initial.frame('human_required', permission());
    if (closeInitial) initial.end();
  });
  await waitFor(() => expect(getPendingApproval()?.token).toBe('first-token'));
  const tab = getTabStoreSnapshot().tabs.find((record) => record.kind === 'content')!;
  act(() => { setMaterializedTabLifecycle(tab.id, 'live'); focusMaterializedTab(tab.id); });
  const reader = await screen.findByText('print("partial")');
  reader.scrollTop = 31;
  return { id: tab.id, reader, decision: screen.getByRole('alertdialog'), initial };
}
async function allow(decision: HTMLElement) {
  fireEvent.click(within(decision).getByRole('button', { name: /^(Allow once|AUTHORIZE)$/ }));
  return stream('first-token');
}
function retained(id: string) {
  return getTabStoreSnapshot().tabs.find((record) => record.id === id)!;
}

it.each([
  ['beginner', 'pass'], ['expert', 'pass'], ['beginner', 'fail'], ['expert', 'fail'],
] as const)('%s retains an observed %s check when replay settles the identical artifact', async (mode, verdict) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => replay.frame('code_chunk', { code: 'print("checked")', language: 'python', filepath: 'src/gated_file.py' }));
  act(() => publishCognition({ type: 'verify', source: 'mirror', data: { verdict, target: 'src/gated_file.py', output: 'Reported check' } }));
  expect(retained(work.id).content?.verifyVerdict).toBe(verdict);
  await act(async () => { replay.frame('done'); replay.end(); });
  await waitFor(() => expect(retained(work.id).content?.streaming).toBe(false));
  expect(retained(work.id).content).toMatchObject({ code: 'print("checked")', verifyVerdict: verdict, verifyOutput: 'Reported check' });
  expect(screen.getByRole('status', { name: verdict === 'pass' ? 'Done' : 'That did not work.' })).toBeVisible();
});
it('does not carry a check onto a different terminal code snapshot', async () => {
  const work = await heldWork('beginner');
  const replay = await allow(work.decision);
  await act(async () => replay.frame('code_chunk', { code: 'print("checked")', language: 'python', filepath: 'src/gated_file.py' }));
  act(() => publishCognition({ type: 'verify', source: 'mirror', data: { verdict: 'pass', target: 'src/gated_file.py' } }));
  await act(async () => { replay.frame('code', { code: 'print("changed")', language: 'python', filepath: 'src/gated_file.py' }); replay.frame('done'); replay.end(); });
  await waitFor(() => expect(retained(work.id).content?.streaming).toBe(false));
  expect(retained(work.id).content?.code).toBe('print("changed")');
  expect(retained(work.id).content?.verifyVerdict).toBeUndefined();
  expect(screen.getByRole('status', { name: 'Finished, but not verified' })).toBeVisible();
});

it.each([
  ['beginner', 'pass', 'code'], ['beginner', 'pass', 'code_chunk'],
  ['beginner', 'fail', 'code_chunk'], ['expert', 'pass', 'code_chunk'], ['expert', 'fail', 'code_chunk'],
] as const)('%s keeps the observed %s check when %s repeats the same replay snapshot', async (mode, verdict, event) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  const snapshot = { code: 'print("checked")', language: 'python', filepath: 'src/gated_file.py' };
  await act(async () => replay.frame('code_chunk', snapshot));
  act(() => publishCognition({ type: 'verify', source: 'mirror', data: { verdict, target: 'src/gated_file.py', output: 'Reported check' } }));
  expect(retained(work.id).content?.verifyVerdict).toBe(verdict);
  await act(async () => { replay.frame(event, snapshot); replay.frame('done'); replay.end(); });
  await waitFor(() => expect(retained(work.id).content?.streaming).toBe(false));
  expect(retained(work.id).content).toMatchObject({ ...snapshot, verifyVerdict: verdict, verifyOutput: 'Reported check' });
  expect(screen.getByText('print("checked")')).toBe(work.reader);
  expect(screen.getByRole('status', { name: verdict === 'pass' ? 'Done' : 'That did not work.' })).toBeVisible();
});

it.each([
  ['code', { code: 'print("changed")', language: 'python', filepath: 'src/gated_file.py' }],
  ['path', { code: 'print("checked")', language: 'python', filepath: 'other/gated_file.py' }],
  ['language', { code: 'print("checked")', language: 'text', filepath: 'src/gated_file.py' }],
] as const)('invalidates the observed replay check when a chunk changes its %s', async (_, changed) => {
  const work = await heldWork('beginner');
  const replay = await allow(work.decision);
  await act(async () => replay.frame('code_chunk', { code: 'print("checked")', language: 'python', filepath: 'src/gated_file.py' }));
  act(() => publishCognition({ type: 'verify', source: 'mirror', data: { verdict: 'pass', target: 'src/gated_file.py', output: 'Reported check' } }));
  expect(retained(work.id).content?.verifyVerdict).toBe('pass');
  await act(async () => { replay.frame('code_chunk', changed); replay.frame('done'); replay.end(); });
  await waitFor(() => expect(retained(work.id).content?.streaming).toBe(false));
  expect(retained(work.id).content).toMatchObject(changed);
  expect(retained(work.id).content?.verifyVerdict).toBeUndefined();
  expect(screen.getByRole('status', { name: 'Finished, but not verified' })).toBeVisible();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s holds the partial reader without pretending to write or finish', async (mode) => {
  const work = await heldWork(mode);
  expect(retained(work.id).content).toMatchObject({ streaming: false, completion: 'awaiting-approval' });
  expect(beingFactsFromStores(useMirrorStore.getState(), getTabStoreSnapshot()).approvalPending).toBe(true);
  expect(screen.getByText(/generation is waiting for your permission/i)).toBeVisible();
  expect(screen.queryByText('Finished, but not verified')).not.toBeInTheDocument();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s preserves the original reader when replay reaches a renewed permission boundary', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => { replay.frame('human_required', permission('second-token')); replay.end(); });
  await waitFor(() => expect(getPendingApproval()?.token).toBe('second-token'));
  expect(retained(work.id)).toMatchObject({ lifecycle: 'live', content: { code: 'print("partial")', streaming: false, completion: 'awaiting-approval' } });
  expect(screen.getByText('print("partial")')).toBe(work.reader);
  expect(work.reader.scrollTop).toBe(31);
  expect(screen.queryByText('Finished, but not verified')).not.toBeInTheDocument();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s retains partial work after replay EOF without done', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => replay.end());
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id)).toMatchObject({ lifecycle: 'live', content: { code: 'print("partial")', streaming: false, completion: 'incomplete' } });
  expect(screen.getByText('print("partial")')).toBe(work.reader);
  expect(screen.getByText(/generation interrupted.*partial result/i)).toBeVisible();
  expect(screen.queryByText('Finished, but not verified')).not.toBeInTheDocument();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s declines the action without hiding the partial reader or claiming completion', async (mode) => {
  const work = await heldWork(mode);
  fireEvent.click(within(work.decision).getByRole('button', { name: /^(Don't allow|REJECT)$/ }));
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id)).toMatchObject({ lifecycle: 'live', content: { code: 'print("partial")', streaming: false, completion: 'declined' } });
  expect(screen.getByText('print("partial")')).toBe(work.reader);
  expect(screen.getByText(/action declined locally.*partial result/i)).toBeVisible();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s completes with replay-owned code, not the approval proposal or a basename guess', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => {
    replay.frame('code', { code: 'print("replayed")', language: 'python', filepath: 'src/gated_file.py' });
    replay.frame('done'); replay.end();
  });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id).content).toMatchObject({ code: 'print("replayed")', language: 'python', filepath: 'src/gated_file.py', streaming: false });
  expect(retained(work.id).content?.completion).toBeUndefined();
  expect(retained(work.id).content?.verifyVerdict).toBeUndefined();
  expect(screen.getByText('print("replayed")')).toBe(work.reader);
  expect(work.reader.scrollTop).toBe(31);
  expect(screen.getByText('Finished, but not verified')).toBeVisible();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s distinguishes submitted permission from an actual replayed code stream', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  const waiting = retained(work.id).content;
  const waitingNotice = screen.queryByText(/permission submitted.*waiting for the replay response/i);
  await act(async () => replay.frame('code_chunk', { code: 'print("replay partial")', language: 'python', filepath: 'src/gated_file.py' }));
  // Finish the controlled stream even on RED so no abandoned request survives
  // test cleanup. Capture the intermediate state before settlement.
  await act(async () => Promise.resolve());
  const streaming = retained(work.id).content;
  await act(async () => replay.end());
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(waiting).toMatchObject({ streaming: false, completion: 'awaiting-replay' });
  expect(waitingNotice).not.toBeNull();
  expect(streaming).toMatchObject({ code: 'print("replay partial")', streaming: true });
  expect(streaming?.completion).toBeUndefined();
  expect(retained(work.id).content).toMatchObject({ code: 'print("replay partial")', streaming: false, completion: 'incomplete' });
  expect(screen.getByText('print("replay partial")')).toBe(work.reader);
});

it('a superseded replay cannot overwrite the new request or emit an old completion receipt', async () => {
  const work = await heldWork('beginner');
  const replay = await allow(work.decision);
  const input = screen.getByRole('textbox', { name: 'Talk to GAGOS' });
  fireEvent.change(input, { target: { value: 'create next.py' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  const next = await stream('next');
  await act(async () => {
    replay.frame('code', { code: 'print("obsolete replay")', language: 'python', filepath: 'src/gated_file.py' });
    replay.frame('done'); replay.end();
    next.frame('code', { code: 'print("next")', language: 'python', filepath: 'next.py' });
    next.frame('done'); next.end();
  });
  await waitFor(() => expect(getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'next.py')?.content?.streaming).toBe(false));
  expect(retained(work.id).content).toMatchObject({ code: 'print("partial")', streaming: false, completion: 'cancelled' });
  expect(screen.queryByText('print("obsolete replay")')).not.toBeInTheDocument();
  expect(screen.queryByText('Finished, but not verified')).not.toBeInTheDocument();
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'next.py')?.content?.code).toBe('print("next")');
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s admits permission hold immediately without waiting for HTTP EOF', async (mode) => {
  const work = await heldWork(mode, false);
  try {
    await waitFor(() => expect(retained(work.id).content).toMatchObject({ streaming: false, completion: 'awaiting-approval' }));
    expect(work.initial.cancellations()).toBe(1);
  } finally {
    await act(async () => work.initial.end());
  }
});

it('done settles the replay immediately and discards queued post-terminal code', async () => {
  const work = await heldWork('beginner');
  const replay = await allow(work.decision);
  await act(async () => {
    replay.frame('code', { code: 'print("terminal")', language: 'python', filepath: 'src/gated_file.py' });
    replay.frame('done');
    replay.frame('code', { code: 'print("post-terminal")', language: 'python', filepath: 'src/gated_file.py' });
  });
  try {
    await waitFor(() => expect(retained(work.id).content).toMatchObject({ code: 'print("terminal")', streaming: false }));
    expect(replay.cancellations()).toBe(1);
    expect(screen.queryByText('print("post-terminal")')).not.toBeInTheDocument();
  } finally {
    await act(async () => replay.end());
  }
});

it('an old verified reader cannot supply completion or verification while the replay response is pending', async () => {
  const work = await heldWork('beginner');
  act(() => {
    const other = showContentSurface({ code: 'print("older verified")', language: 'python', filepath: 'older.py', streaming: false, verifyVerdict: 'pass' });
    focusMaterializedTab(other.id);
  });
  const heldFacts = beingFactsFromStores(useMirrorStore.getState(), getTabStoreSnapshot());
  const replay = await allow(work.decision);
  const pendingFacts = beingFactsFromStores(useMirrorStore.getState(), getTabStoreSnapshot());
  await act(async () => replay.end());
  expect(heldFacts.taskActivity).toBe('idle');
  expect(heldFacts.verification).toBe('unknown');
  expect(pendingFacts.taskActivity).toBe('awaiting-replay');
  expect(pendingFacts.verification).toBe('unknown');
});

it.each(['authorize', 'decline'])('a stale %s capability cannot replace the current visible decision', async (action) => {
  const work = await heldWork('beginner');
  let decision;
  await act(async () => {
    decision = action === 'authorize'
      ? await approvePendingApproval({ expectedToken: 'obsolete-token' })
      : await rejectPendingApproval('obsolete-token');
  });
  expect(decision).toMatchObject(action === 'authorize' ? { ok: false, paused: false } : { confirmed: false });
  expect(getPendingApproval()?.token).toBe('first-token');
  expect(work.decision).toBeVisible();
  expect(retained(work.id).content?.completion).toBe('awaiting-approval');
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s keeps replay-owned fenced text at terminal settlement instead of the proposal', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => {
    replay.frame('text_chunk', { text: '```python\nprint("text replay")\n```' });
    replay.frame('done'); replay.end();
  });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id).content).toMatchObject({ code: 'print("text replay")', language: 'python', filepath: 'src/gated_file.py', streaming: false });
  expect(retained(work.id).content?.completion).toBeUndefined();
  expect(screen.getByText('print("text replay")')).toBe(work.reader);
  expect(work.reader.scrollTop).toBe(31);
  expect(screen.queryByText('print("proposal")')).not.toBeInTheDocument();
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s keeps the code snapshot admitted immediately before permission, including after decline', async (mode) => {
  const work = await heldWork(mode, true, 'code');
  expect(retained(work.id).content).toMatchObject({ code: 'print("partial")', filepath: 'src/gated_file.py', streaming: false, completion: 'awaiting-approval' });
  fireEvent.click(within(work.decision).getByRole('button', { name: /^(Don't allow|REJECT)$/ }));
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id)).toMatchObject({ lifecycle: 'live', content: { code: 'print("partial")', streaming: false, completion: 'declined' } });
  expect(screen.getByText('print("partial")')).toBe(work.reader);
  expect(work.reader.scrollTop).toBe(31);
});

it.each<ExperienceMode>(['beginner', 'expert'])('%s does not promote a proposed file when the completed replay supplies no artifact', async (mode) => {
  const work = await heldWork(mode);
  const replay = await allow(work.decision);
  await act(async () => { replay.frame('done'); replay.end(); });
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(retained(work.id).content).toMatchObject({ code: 'print("partial")', streaming: false, completion: 'incomplete' });
  expect(screen.getByText('print("partial")')).toBe(work.reader);
  expect(screen.queryByText('print("proposal")')).not.toBeInTheDocument();
  expect(screen.queryByText('Finished, but not verified')).not.toBeInTheDocument();
});
