import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useWorkMaterialization } from './useWorkMaterialization';
import { LivingWorkspaceShell } from '../../livingMirror/LivingWorkspaceShell';
import {
  __resetTabStoreForTests, focusWorkspace, getTabStoreSnapshot,
  pinWorkspace, setMaterializedTabLifecycle, closeWorkspace, finishMaterializedTabRetraction,
  showContentSurface,
  isWorkMaterializationClaimed,
  updateMaterializedTab,
  clearMaterializedTab,
} from '../../superbrain/lib/tabStore';
import { setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { sendDirective } from '../../superbrain/lib/aiosAdapter';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';

const initialMirror = useMirrorStore.getState();

// Substitute only the backend request, not submission/intent/materialization,
// retained identities, focus, queue or the readable work plane.
vi.mock('../../superbrain/lib/aiosAdapter', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../superbrain/lib/aiosAdapter')>(),
  sendDirective: vi.fn(async () => ({ ok: true, paused: false, answer: '```python\nprint("completed")\n```' })),
  fetchOnboardingState: vi.fn(async () => ({})),
}));

beforeEach(() => {
  __resetTabStoreForTests();
  setConversationPhase('idle');
  vi.mocked(sendDirective).mockReset().mockResolvedValue({ ok: true, paused: false, answer: '```python\nprint("completed")\n```' });
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })));
});
afterEach(() => { cleanup(); __resetTabStoreForTests(); useMirrorStore.setState(initialMirror); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function mountWork() {
  const hook = renderHook(() => useWorkMaterialization({ setOnline: () => {}, setMilestones: () => {}, chatModelId: 'auto' }));
  render(<LivingWorkspaceShell experienceMode="expert" />);
  return hook;
}

it('keeps an interrupted partial readable and explicitly incomplete through Close and Reopen', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    return { ok: false, paused: false, answer: 'Connection interrupted.' };
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  const partial = getTabStoreSnapshot().tabs[0];
  const reader = screen.getByText('print("partial")');
  expect(reader).toBeVisible();
  expect(partial).toMatchObject({ content: { streaming: false, completion: 'incomplete' } });
  expect(partial.lifecycle).not.toBe('retracting');
  expect(screen.getByText('Generation interrupted. Partial result; no completed outcome is established.')).toBeVisible();
  reader.scrollTop = 37;
  act(() => {
    closeWorkspace(partial.id);
    finishMaterializedTabRetraction(partial.id, getTabStoreSnapshot().tabs[0].retractionToken);
  });
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' })).getByRole('button', { name: 'Recent observations' }));
  expect(within(screen.getByRole('region', { name: 'Closed results' })).getByText('Generation interrupted. Partial result; no completed outcome is established.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Reopen partial.py' }));
  expect(screen.getByText('print("partial")')).toBe(reader);
  expect(reader.scrollTop).toBe(37);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id: partial.id, content: { streaming: false, completion: 'incomplete' } });
  expect(vi.mocked(sendDirective)).toHaveBeenCalledTimes(1);
});

it('settles partial code and releases writing ownership when the request throws', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, _onChunk, onCode) => {
    onCode?.('print("partial")', 'python');
    throw new TypeError('Failed to fetch');
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ content: { streaming: false, completion: 'incomplete', code: 'print("partial")' } });
  expect(screen.getByText('print("partial")')).toBeVisible();
  expect(work.current.busy).toBe(false);
  expect(isWorkMaterializationClaimed()).toBe(false);
});

it('marks only local cancellation and ignores old chunks or completion during a newer turn', async () => {
  const { result: work } = mountWork();
  let finishOld!: (value: Awaited<ReturnType<typeof sendDirective>>) => void;
  let finishNew!: typeof finishOld;
  let oldChunk!: NonNullable<Parameters<typeof sendDirective>[2]>;
  let oldSignal!: AbortSignal;
  vi.mocked(sendDirective).mockImplementationOnce((_text, signal, onChunk) => {
    oldSignal = signal!;
    oldChunk = onChunk!;
    onChunk?.('```python\nprint("partial")');
    return new Promise((resolve) => { finishOld = resolve; });
  }).mockImplementationOnce(() => new Promise((resolve) => { finishNew = resolve; }));
  let oldTurn!: Promise<void>;
  act(() => { oldTurn = work.current.submit('create partial.py'); });
  const reader = screen.getByText('print("partial")');
  act(() => work.current.stopTurn());
  expect(oldSignal.aborted).toBe(true);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ content: { streaming: false, completion: 'cancelled' } });
  expect(screen.getByText('Generation cancelled locally. Partial result retained; backend termination is unconfirmed.')).toBeVisible();
  let newTurn!: Promise<void>;
  act(() => { newTurn = work.current.submit('create next.py'); });
  await act(async () => {
    oldChunk('```python\nprint("late overwrite")');
    finishOld({ ok: true, paused: false, answer: '```python\nprint("late complete")\n```' });
    await oldTurn;
  });
  expect(isWorkMaterializationClaimed()).toBe(true);
  expect(work.current.busy).toBe(true);
  expect(screen.getByText('print("partial")')).toBe(reader);
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'partial.py')).toMatchObject({ content: { code: 'print("partial")', completion: 'cancelled' } });
  await act(async () => {
    finishNew({ ok: true, paused: false, answer: '```python\nprint("next")\n```' });
    await newTurn;
  });
  expect(isWorkMaterializationClaimed()).toBe(false);
});

it('does not keep an empty writing placeholder after failure', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockRejectedValueOnce(new TypeError('Failed to fetch'));
  await act(async () => { await work.current.submit('create empty.py'); });
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ lifecycle: 'retracting', content: { streaming: false } });
  expect(isWorkMaterializationClaimed()).toBe(false);
});

it('a same-file retry clears the previous partial outcome and verifier before new work arrives', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    return { ok: false, paused: false, answer: '' };
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  const partial = getTabStoreSnapshot().tabs[0];
  const reader = screen.getByText('print("partial")');
  act(() => updateMaterializedTab(partial.id, { content: { ...partial.content!, verifyVerdict: 'pass', verifyOutput: 'prior check' } }));
  let finish!: (value: Awaited<ReturnType<typeof sendDirective>>) => void;
  vi.mocked(sendDirective).mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
  let turn!: Promise<void>;
  act(() => { turn = work.current.submit('create partial.py'); });
  const writing = getTabStoreSnapshot().tabs[0];
  expect(writing.id).toBe(partial.id);
  expect(writing.content?.completion).toBeUndefined();
  expect(writing.content?.verifyVerdict).toBeUndefined();
  expect(writing.content?.verifyOutput).toBeUndefined();
  expect(writing.content?.streaming).toBe(true);
  await act(async () => {
    finish({ ok: true, paused: false, answer: '```python\nprint("completed")\n```' });
    await turn;
  });
  expect(screen.getByText('print("completed")')).toBe(reader);
  expect(getTabStoreSnapshot().tabs[0].content).toMatchObject({ streaming: false });
  expect(getTabStoreSnapshot().tabs[0].content?.completion).toBeUndefined();
});

it('settles an unexpected AbortError without claiming backend termination', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    throw new DOMException('Transport aborted', 'AbortError');
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ content: { streaming: false, completion: 'incomplete' } });
  expect(work.current.busy).toBe(false);
  expect(isWorkMaterializationClaimed()).toBe(false);
  expect(screen.getByText('print("partial")')).toBeVisible();
});

it('the real composer Stop cancels locally and the same cancelled reader reopens', async () => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
  const { default: GagosChrome } = await import('../GagosChrome');
  render(<><LivingWorkspaceShell experienceMode="expert" /><GagosChrome integrated experienceMode="expert" /></>);
  let finish!: (value: Awaited<ReturnType<typeof sendDirective>>) => void;
  let signal!: AbortSignal;
  vi.mocked(sendDirective).mockImplementationOnce((_text, requestSignal, onChunk) => {
    signal = requestSignal!;
    onChunk?.('```python\nprint("partial")');
    return new Promise((resolve) => { finish = resolve; });
  });
  const chrome = within(screen.getByLabelText('GAGOS conversation'));
  fireEvent.change(chrome.getByRole('textbox'), { target: { value: 'create partial.py' } });
  fireEvent.click(chrome.getByRole('button', { name: 'Send' }));
  const reader = screen.getByText('print("partial")');
  fireEvent.click(chrome.getByRole('button', { name: 'Stop' }));
  expect(signal.aborted).toBe(true);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ content: { streaming: false, completion: 'cancelled' } });
  const partial = getTabStoreSnapshot().tabs[0];
  act(() => {
    closeWorkspace(partial.id);
    finishMaterializedTabRetraction(partial.id, getTabStoreSnapshot().tabs[0].retractionToken);
  });
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' })).getByRole('button', { name: 'Recent observations' }));
  expect(within(screen.getByRole('region', { name: 'Closed results' })).getByText('Generation cancelled locally. Partial result retained; backend termination is unconfirmed.')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Reopen partial.py' }));
  expect(screen.getByText('print("partial")')).toBe(reader);
  expect(reader).toBeVisible();
  await act(async () => { finish({ ok: true, paused: false, answer: 'late' }); });
  expect(getTabStoreSnapshot().tabs[0].content?.completion).toBe('cancelled');
  expect(vi.mocked(sendDirective)).toHaveBeenCalledTimes(1);
});

it.each(['incomplete', 'cancelled'] as const)('Close/History cannot turn the latest %s generation into older completed work', async (completion) => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
  // An explicitly admitted mirror fixture, not evidence of a live backend.
  useMirrorStore.setState({ status: 'online', connection: 'connected', projection: 'fresh', phase: 'idle', snapshotReceivedAt: '2026-10-03T00:00:00Z' });
  const { default: GagosChrome } = await import('../GagosChrome');
  render(<><LivingWorkspaceShell experienceMode="expert" /><GagosChrome integrated experienceMode="expert" /></>);
  const chrome = within(screen.getByLabelText('GAGOS conversation'));
  await act(async () => {
    fireEvent.change(chrome.getByRole('textbox'), { target: { value: 'create older.py' } });
    fireEvent.click(chrome.getByRole('button', { name: 'Send' }));
  });
  let finish!: (value: Awaited<ReturnType<typeof sendDirective>>) => void;
  vi.mocked(sendDirective).mockImplementationOnce((_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    return new Promise((resolve) => { finish = resolve; });
  });
  fireEvent.change(chrome.getByRole('textbox'), { target: { value: 'create partial.py' } });
  fireEvent.click(chrome.getByRole('button', { name: 'Send' }));
  const partial = getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'partial.py')!;
  act(() => focusWorkspace(partial.id));
  if (completion === 'cancelled') fireEvent.click(chrome.getByRole('button', { name: 'Stop' }));
  await act(async () => { finish({ ok: false, paused: false, answer: 'Interrupted.' }); });
  // The terminal visual beat may decay; outcome must not decay with it.
  vi.spyOn(performance, 'now').mockReturnValue(performance.now() + 10_000);
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  act(() => finishMaterializedTabRetraction(partial.id, getTabStoreSnapshot().tabs.find((tab) => tab.id === partial.id)?.retractionToken));
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' })).getByRole('button', { name: 'Recent observations' }));
  expect(screen.getByRole('status', { name: 'GAGOS organism status' })).toHaveTextContent('GAGOS could not complete the action.');
  expect(getTabStoreSnapshot().recoverableTabs?.find((tab) => tab.id === partial.id)?.content?.completion).toBe(completion);
  fireEvent.click(screen.getByRole('button', { name: 'Reopen partial.py' }));
  expect(screen.getByRole('status', { name: 'GAGOS organism status' })).toHaveTextContent('GAGOS could not complete the action.');
  await act(async () => {
    fireEvent.change(chrome.getByRole('textbox'), { target: { value: 'create next.py' } });
    fireEvent.click(chrome.getByRole('button', { name: 'Send' }));
  });
  expect(screen.getByRole('status', { name: 'GAGOS organism status' })).toHaveTextContent('GAGOS finished the work, but it is not verified yet.');
});

it.each(['text', 'code'])('ignores a delayed %s callback after partial failure has settled', async (kind) => {
  const { result: work } = mountWork();
  let late!: () => void;
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk, onCode) => {
    onChunk?.('```python\nprint("partial")');
    late = () => kind === 'text' ? onChunk?.('```python\nprint("late")') : onCode?.('print("late")', 'python');
    return { ok: false, paused: false, answer: 'Interrupted.' };
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  act(late);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ content: { streaming: false, completion: 'incomplete', code: 'print("partial")' } });
  expect(isWorkMaterializationClaimed()).toBe(false);
  expect(work.current.busy).toBe(false);
});

it('whole-session privacy cleanup also clears the retained local generation outcome', async () => {
  const { result: work } = mountWork();
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    return { ok: false, paused: false, answer: 'Interrupted.' };
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  expect(getTabStoreSnapshot()).toMatchObject({ workResultOutcome: { completion: 'incomplete' } });
  act(() => clearMaterializedTab());
  expect(getTabStoreSnapshot()).toMatchObject({ tabs: [], recoverableTabs: [], workResultOutcome: null });
});

it('retains the current pinned result and DOM through six real same-file submissions', async () => {
  const { result: work } = mountWork();
  await act(async () => { await work.current.submit('create result.py'); });
  const initial = getTabStoreSnapshot().tabs[0];
  const text = screen.getByText('print("completed")');
  act(() => { pinWorkspace(initial.id); setMaterializedTabLifecycle(initial.id, 'live'); });
  text.focus();
  for (let turn = 2; turn <= 6; turn += 1) {
    await act(async () => { await work.current.submit('create result.py'); });
    expect(getTabStoreSnapshot()).toMatchObject({ focusId: initial.id, tabs: [{
      id: initial.id, seatIndex: initial.seatIndex, pinned: true, lifecycle: 'live',
      content: { filepath: 'result.py', streaming: false, code: 'print("completed")' },
    }] });
    expect(screen.getByText('print("completed")')).toBe(text);
    expect(text).toHaveFocus();
  }
});

it('evicts only an older unprotected surface, not pinned work or the selected reader', async () => {
  const { result: work } = mountWork();
  const ids: string[] = [];
  for (let turn = 1; turn <= 6; turn += 1) {
    await act(async () => { await work.current.submit(`create result${turn}.py`); });
    const tab = getTabStoreSnapshot().tabs.find((candidate) => candidate.content?.filepath === `result${turn}.py`)!;
    ids.push(tab.id);
    act(() => {
      setMaterializedTabLifecycle(tab.id, 'live');
      if (turn === 1) pinWorkspace(tab.id);
      if (turn === 2) focusWorkspace(tab.id);
    });
  }
  const tabs = getTabStoreSnapshot().tabs;
  expect(tabs.find((tab) => tab.id === ids[0])).toMatchObject({ pinned: true, lifecycle: 'live' });
  expect(tabs.find((tab) => tab.id === ids[1])).toMatchObject({ lifecycle: 'live' });
  expect(tabs.find((tab) => tab.id === ids[2])).toMatchObject({ lifecycle: 'retracting' });
  expect(tabs.find((tab) => tab.id === ids[5])).toMatchObject({ lifecycle: 'live', content: { streaming: false } });
  expect(getTabStoreSnapshot().focusId).toBe(ids[1]);
});

it('reopens a real submitted result after geometry retires without resubmitting or replacing the reading DOM', async () => {
  const { result: work } = mountWork();
  await act(async () => { await work.current.submit('create result.py'); });
  const initial = getTabStoreSnapshot().tabs[0];
  const output = screen.getByText('print("completed")');
  act(() => {
    closeWorkspace(initial.id);
    const token = getTabStoreSnapshot().tabs[0].retractionToken;
    finishMaterializedTabRetraction(initial.id, token);
  });
  fireEvent.click(within(screen.getByRole('navigation', { name: 'Workspaces' }))
    .getByRole('button', { name: 'Recent observations' }));
  fireEvent.click(screen.getByRole('button', { name: 'Reopen result.py' }));
  expect(getTabStoreSnapshot().focusId).toBe(initial.id);
  expect(screen.getByText('print("completed")')).toBe(output);
  expect(work.current.messages.filter((message: { role: string }) => message.role === 'user')).toHaveLength(1);
});

it('a same-file submission during retraction resumes one result and consumes its closed copy', async () => {
  const { result: work } = mountWork();
  await act(async () => { await work.current.submit('create result.py'); });
  const initial = getTabStoreSnapshot().tabs[0];
  const output = screen.getByText('print("completed")');
  act(() => closeWorkspace(initial.id));
  const staleToken = getTabStoreSnapshot().tabs[0].retractionToken;
  await act(async () => { await work.current.submit('create result.py'); });
  act(() => finishMaterializedTabRetraction(initial.id, staleToken));
  expect(getTabStoreSnapshot().recoverableTabs ?? []).toHaveLength(0);
  expect(getTabStoreSnapshot().tabs.filter((tab) => tab.kind === 'content')).toHaveLength(1);
  expect(screen.getAllByText('print("completed")')).toEqual([output]);
  expect(output).toBeVisible();
});

it('keeps a partial result in real work tracking when a failed turn cannot close into a full recovery cache', async () => {
  const { result: work } = mountWork();
  act(() => {
    for (let n = 0; n < 12; n++) {
      const saved = showContentSurface({ filepath: `saved${n}.py`, language: 'python', code: 'older result' });
      closeWorkspace(saved.id);
      finishMaterializedTabRetraction(saved.id, getTabStoreSnapshot().tabs.find((tab) => tab.id === saved.id)?.retractionToken);
    }
  });
  vi.mocked(sendDirective).mockImplementationOnce(async (_text, _signal, onChunk) => {
    onChunk?.('```python\nprint("partial")');
    return { ok: false, paused: false, answer: 'Response interrupted.' };
  });
  await act(async () => { await work.current.submit('create partial.py'); });
  const partial = getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'partial.py')!;
  expect(partial.lifecycle).not.toBe('retracting');
  expect(screen.getByText('print("partial")')).toBeVisible();
  expect(work.current.workTabIdsRef.current).toContain(partial.id);
  expect(getTabStoreSnapshot().recoverableTabs).toHaveLength(12);
  expect(work.current.messages.some((message: { text: string }) => /interrupted before completion/.test(message.text))).toBe(true);
});

it('keeps Guided Forget reachable with twelve retained submissions and twelve occupied body anchors', async () => {
  vi.stubGlobal('matchMedia', vi.fn((query: string) => ({
    matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn(),
  })));
  const { result: work } = mountWork();
  const { default: GagosChrome } = await import('../GagosChrome');
  render(<GagosChrome integrated experienceMode="beginner" />);
  for (let n = 0; n < 24; n++) {
    await act(async () => { await work.current.submit(`create result${n}.py`); });
    act(() => {
      const tab = getTabStoreSnapshot().tabs.find((record) => record.content?.filepath === `result${n}.py`)!;
      setMaterializedTabLifecycle(tab.id, 'live');
      pinWorkspace(tab.id);
      if (n < 12) {
        closeWorkspace(tab.id);
        finishMaterializedTabRetraction(tab.id, getTabStoreSnapshot().tabs.find((record) => record.id === tab.id)?.retractionToken);
      }
    });
  }
  const before = getTabStoreSnapshot();
  const current = before.tabs.find((record) => record.content?.filepath === 'result23.py')!;
  const seats = before.tabs.map((record) => record.seatIndex);
  expect(before.recoverableTabs).toHaveLength(12);
  expect(new Set(seats).size).toBe(12);
  act(() => focusWorkspace(current.id));
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  expect(getTabStoreSnapshot().tabs.find((record) => record.id === current.id)?.lifecycle).toBe('live');
  fireEvent.click(within(screen.getByLabelText('GAGOS conversation')).getByRole('button', { name: 'Recent activity' }));
  fireEvent.click(screen.getByRole('button', { name: 'Forget result0.py' }));
  fireEvent.click(screen.getByRole('button', { name: 'Forget permanently' }));
  expect(getTabStoreSnapshot().panels?.find((panel) => panel.id === 'history'))
    .toMatchObject({ seatIndex: null, open: true });
  expect(getTabStoreSnapshot().tabs.map((record) => record.seatIndex)).toEqual(seats);
  expect(screen.getByText(/Recent activity is available without a body anchor/)).toBeVisible();
  expect(getTabStoreSnapshot().recoverableTabs).toHaveLength(11);
  act(() => focusWorkspace(current.id));
  fireEvent.click(screen.getByRole('button', { name: 'Close workspace' }));
  expect(getTabStoreSnapshot().recoverableTabs?.some((record) => record.id === current.id)).toBe(true);
  expect(getTabStoreSnapshot().recoverableTabs).toHaveLength(12);
  expect(vi.mocked(sendDirective)).toHaveBeenCalledTimes(24);
});
