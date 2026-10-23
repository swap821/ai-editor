import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { StrictMode } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useWorkMaterialization } from './useWorkMaterialization';
import { __resetAiosAdapterForTests, getPendingApproval, type OnboardingState } from '../../superbrain/lib/aiosAdapter';
import { __resetTabStoreForTests, getTabStoreSnapshot, isWorkMaterializationClaimed } from '../../superbrain/lib/tabStore';
import { getConversationPhase, setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';
import { getReplyVoice } from '../../superbrain/lib/replyVoiceBus';

type ChatStream = { signal?: AbortSignal | null; frame: (event: string, data?: object) => void; end: () => void };
const streams = new Map<string, ChatStream>();
const turns: Promise<void>[] = [];
const initialMirror = useMirrorStore.getState();
let draining = false;
let onboardingResponse: Promise<Response> | undefined;
let releaseOnboarding: ((response: Response) => void) | undefined;

// Only the wire is controlled. The installed SSE parser, chat adapter,
// generation owner, message list and conversation phase run together.
beforeEach(() => {
  streams.clear();
  turns.length = 0;
  draining = false;
  onboardingResponse = undefined;
  releaseOnboarding = undefined;
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  setConversationPhase('idle');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/api/v1/auth/session')) {
      return new Response(JSON.stringify({ authenticated: true }));
    }
    if (String(url).endsWith('/api/v1/onboarding/state') && onboardingResponse) return onboardingResponse;
    if (String(url).endsWith('/api/v1/chat') || String(url).endsWith('/api/generate')) {
      const request = JSON.parse(String(init?.body));
      const prompt = (request.transcript ?? request.messages[0].content[0].text) as string;
      let closed = false;
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          if (draining) { closed = true; controller.close(); return; }
          streams.set(prompt, {
            signal: init?.signal,
            frame: (event, data = {}) => {
              if (!closed) controller.enqueue(new TextEncoder().encode(
                'event: ' + event + '\ndata: ' + JSON.stringify(data) + '\n\n',
              ));
            },
            end: () => { if (!closed) { closed = true; controller.close(); } },
          });
        },
        cancel() { closed = true; },
      });
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    }
    return new Response('{}', { status: 503 });
  }));
});
async function finishChatTest(restoreTransports = () => vi.unstubAllGlobals()) {
  // Failed assertions may leave a reader suspended. Let the real hook finish
  // under its fake transport before retiring shared state or globals.
  await act(async () => {
    draining = true;
    releaseOnboarding?.(new Response('{}', { status: 503 }));
    for (const stream of streams.values()) stream.end();
    await Promise.allSettled(turns);
  });
  cleanup();
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  useMirrorStore.setState(initialMirror);
  setConversationPhase('idle');
  restoreTransports();
}
afterEach(() => finishChatTest());

function mountChat(options: {
  setMilestones?: (state: OnboardingState) => void;
  setOnline?: (online: boolean) => void;
} = {}) {
  return renderHook(() => useWorkMaterialization({
    setOnline: () => {}, setMilestones: () => {}, chatModelId: 'auto',
    ...options,
  }));
}
function submitChat(owner: ReturnType<typeof useWorkMaterialization>, prompt: string) {
  const turn = owner.submit(prompt);
  turns.push(turn);
  return turn;
}
async function streamFor(prompt: string) {
  await waitFor(() => expect(streams.has(prompt)).toBe(true));
  return streams.get(prompt)!;
}

it('chat stream: updates one stable readable message before the done frame', async () => {
  const { result } = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(result.current, 'Explain this idea'); });
  const stream = await streamFor('Explain this idea');
  await act(async () => { stream.frame('text_chunk', { text: 'An actual ' }); });
  await waitFor(() => expect(result.current.messages.find(message => message.role === 'gagos')?.text).toBe('An actual '));
  const replyId = result.current.messages.find(message => message.role === 'gagos')!.id;
  expect(getConversationPhase()).toBe('streaming');
  expect(result.current.messages.find(message => message.id === replyId)?.streaming).toBe(true);
  await act(async () => { stream.frame('text_chunk', { text: 'answer' }); });
  expect(result.current.messages.filter(message => message.role === 'gagos')).toMatchObject([
    { id: replyId, text: 'An actual answer', streaming: true },
  ]);
  await act(async () => { stream.frame('done'); stream.end(); await turn; });
  expect(result.current.messages.filter(message => message.role === 'gagos')).toMatchObject([
    { id: replyId, text: 'An actual answer', streaming: false },
  ]);
  expect(getConversationPhase()).toBe('complete');
  expect(result.current.busy).toBe(false);
});

it.each(['eof', 'error'] as const)('chat stream: retains partial text without completion after %s', async (ending) => {
  const { result } = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(result.current, 'Explain a partial idea'); });
  const stream = await streamFor('Explain a partial idea');
  await act(async () => {
    stream.frame('text_chunk', { text: 'The received partial explanation' });
    if (ending === 'error') stream.frame('error', { text: 'Provider interrupted' });
    stream.end();
    await turn;
  });
  expect(getConversationPhase()).toBe('error');
  const replies = result.current.messages.filter(message => message.role === 'gagos');
  expect(replies).toHaveLength(1);
  expect(replies[0].text).toContain('The received partial explanation');
  expect(replies[0].text).toMatch(/interrupted/i);
  expect(replies[0]).toMatchObject({ streaming: false, retry: 'Explain a partial idea' });
  expect(result.current.busy).toBe(false);
});

it('chat stream: Stop retains partial text and draft while late old frames cannot settle a new reply', async () => {
  const { result } = mountChat();
  let oldTurn!: Promise<void>;
  act(() => { oldTurn = submitChat(result.current, 'Explain the old idea'); });
  const old = await streamFor('Explain the old idea');
  await act(async () => { old.frame('text_chunk', { text: 'Old partial text' }); });
  await waitFor(() => expect(result.current.messages.some(message => message.text === 'Old partial text')).toBe(true));
  act(() => { result.current.setDraft('Keep this unsent draft'); result.current.stopTurn(); });
  expect(result.current.draft).toBe('Keep this unsent draft');
  expect(result.current.messages.find(message => message.text === 'Old partial text')).toMatchObject({ streaming: false });
  expect(result.current.busy).toBe(false);
  let newTurn!: Promise<void>;
  act(() => { newTurn = submitChat(result.current, 'Explain the new idea'); });
  const fresh = await streamFor('Explain the new idea');
  await act(async () => { fresh.frame('text_chunk', { text: 'New current text' }); });
  act(() => { result.current.setDraft('New unsent draft'); });
  await act(async () => { old.frame('text_chunk', { text: ' obsolete' }); old.end(); await oldTurn; });
  expect(result.current.messages.find(message => message.text === 'New current text')).toMatchObject({ streaming: true });
  expect(result.current.messages.some(message => message.text.includes('obsolete'))).toBe(false);
  expect(getConversationPhase()).toBe('streaming');
  expect(result.current.draft).toBe('New unsent draft');
  await act(async () => { fresh.frame('done'); fresh.end(); await newTurn; });
  expect(result.current.messages.find(message => message.text === 'New current text')).toMatchObject({ streaming: false });
  expect(getConversationPhase()).toBe('complete');
});

it.each([false, true])('chat lifetime: unmount cannot complete or speak over a successor (overlap: %s)', async (overlap) => {
  const retiredMilestones = vi.fn();
  const retiredOnline = vi.fn();
  const retired = mountChat({ setMilestones: retiredMilestones, setOnline: retiredOnline });
  const staleOwner = retired.result.current;
  let oldTurn!: Promise<void>;
  act(() => { oldTurn = submitChat(staleOwner, 'Explain an abandoned idea'); });
  const old = await streamFor('Explain an abandoned idea');
  await act(async () => { old.frame('text_chunk', { text: 'Abandoned partial' }); });
  if (!overlap) retired.unmount();
  const current = mountChat();
  let newTurn!: Promise<void>;
  act(() => { newTurn = submitChat(current.result.current, 'Explain the current idea'); });
  const fresh = await streamFor('Explain the current idea');
  await act(async () => { fresh.frame('text_chunk', { text: 'Current partial' }); });
  if (overlap) retired.unmount();
  expect(getConversationPhase()).toBe('streaming');
  // The wire deliberately ignores abort. A retired owner must invalidate its
  // callbacks as well as requesting transport cancellation.
  await act(async () => {
    old.frame('text_chunk', { text: ' obsolete tail' });
    old.frame('done'); old.end(); await oldTurn;
  });
  expect(getConversationPhase()).toBe('streaming');
  expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Current partial' });
  expect(old.signal?.aborted).toBe(true);
  expect(retiredOnline).not.toHaveBeenCalled();
  expect(retiredMilestones).not.toHaveBeenCalled();
  await act(async () => { fresh.frame('done'); fresh.end(); await newTurn; });
  expect(getConversationPhase()).toBe('complete');
});

it('chat lifetime: stale submit and Stop handles do not affect the next owner', async () => {
  const retired = mountChat();
  const stale = retired.result.current;
  retired.unmount();
  const current = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(current.result.current, 'Explain the live idea'); });
  const fresh = await streamFor('Explain the live idea');
  await act(async () => { fresh.frame('text_chunk', { text: 'Live text' }); });
  const calls = vi.mocked(fetch).mock.calls.length;
  act(() => { submitChat(stale, 'Explain a stale submission'); stale.stopTurn(); });
  expect(getReplyVoice()).toMatchObject({ phase: 'streaming', text: 'Live text' });
  expect(getConversationPhase()).toBe('streaming');
  await act(async () => { await Promise.resolve(); });
  expect(vi.mocked(fetch).mock.calls).toHaveLength(calls);
  await act(async () => { fresh.frame('done'); fresh.end(); await turn; });
});

it('chat lifetime: StrictMode replay leaves the surviving owner usable', async () => {
  const { result } = renderHook(() => useWorkMaterialization({
    setOnline: () => {}, setMilestones: () => {}, chatModelId: 'auto',
  }), { wrapper: StrictMode });
  let turn!: Promise<void>;
  act(() => { turn = submitChat(result.current, 'Explain strict ownership'); });
  const fresh = await streamFor('Explain strict ownership');
  await act(async () => {
    fresh.frame('text_chunk', { text: 'Surviving owner' });
    fresh.frame('done'); fresh.end(); await turn;
  });
  expect(result.current.busy).toBe(false);
  expect(result.current.messages.find(message => message.role === 'gagos')).toMatchObject({ text: 'Surviving owner', streaming: false });
  expect(getConversationPhase()).toBe('complete');
});

it('chat lifetime: a parent refresh already in flight cannot update after unmount', async () => {
  const milestones = vi.fn();
  onboardingResponse = new Promise<Response>(resolve => { releaseOnboarding = resolve; });
  const owner = mountChat({ setMilestones: milestones });
  let turn!: Promise<void>;
  act(() => { turn = submitChat(owner.result.current, 'Explain refresh ownership'); });
  const fresh = await streamFor('Explain refresh ownership');
  await act(async () => {
    fresh.frame('text_chunk', { text: 'A completed reply' });
    fresh.frame('done'); fresh.end(); await turn;
  });
  owner.unmount();
  await act(async () => {
    releaseOnboarding!(new Response(JSON.stringify({ firstDirective: true })));
    await onboardingResponse;
  });
  expect(milestones).not.toHaveBeenCalled();
});

it.each(['empty', 'partial', 'complete', 'held'] as const)('work lifetime: disposal preserves %s work without inventing completion or approval', async (state) => {
  const owner = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(owner.result.current, 'Create owned.py'); });
  const wire = await streamFor('Create owned.py');
  if (state !== 'empty') await act(async () => {
    wire.frame('code_chunk', { code: 'print("retained")', language: 'python', filepath: 'owned.py' });
  });
  if (state === 'held' || state === 'complete') await act(async () => {
    wire.frame(state === 'held' ? 'human_required' : 'done', { input: { approvalToken: 'held-owner-token' } });
    wire.end(); await turn;
  });
  const before = getTabStoreSnapshot();
  const id = before.tabs[0].id;
  const approval = getPendingApproval();
  const claim = isWorkMaterializationClaimed();
  owner.unmount();
  await act(async () => {
    wire.frame('code', { code: 'obsolete replacement', filepath: 'owned.py' });
    wire.frame('done'); wire.end(); await turn;
  });
  const after = getTabStoreSnapshot();
  const tab = [...after.tabs, ...(after.recoverableTabs || [])].find(record => record.id === id)!;
  if (state === 'empty') {
    expect(tab.lifecycle).toBe('retracting');
    expect(tab.content).toMatchObject({ code: '', streaming: false, completion: 'incomplete' });
  } else {
    expect(tab.content).toMatchObject({ code: 'print("retained")', streaming: false });
    expect(tab.content?.completion).toBe(state === 'held' ? 'awaiting-approval' : state === 'partial' ? 'incomplete' : undefined);
    expect(tab.lifecycle).not.toBe('retracting');
  }
  expect(after.workResultOutcome).toEqual(before.workResultOutcome);
  expect(getPendingApproval()).toBe(approval);
  if (state === 'held') expect(approval).not.toBeNull();
  expect(isWorkMaterializationClaimed()).toBe(claim);
});

it.each(['empty', 'partial', 'complete', 'held'] as const)('work lifetime: removing an old owner cannot alter its same-file successor (%s)', async (state) => {
  const first = mountChat();
  let oldTurn!: Promise<void>;
  act(() => { oldTurn = submitChat(first.result.current, 'Create shared.py first'); });
  const old = await streamFor('Create shared.py first');
  await act(async () => { old.frame('code_chunk', { code: 'old content', filepath: 'shared.py' }); });
  const id = getTabStoreSnapshot().tabs[0].id;
  const second = mountChat();
  let newTurn!: Promise<void>;
  act(() => { newTurn = submitChat(second.result.current, 'Create shared.py second'); });
  const fresh = await streamFor('Create shared.py second');
  if (state !== 'empty') await act(async () => { fresh.frame('code_chunk', { code: 'successor content', filepath: 'shared.py' }); });
  if (state === 'complete' || state === 'held') await act(async () => {
    fresh.frame(state === 'complete' ? 'done' : 'human_required', { input: { approvalToken: 'successor-token' } });
    fresh.end(); await newTurn;
  });
  const before = getTabStoreSnapshot().tabs.find(tab => tab.id === id)!;
  first.unmount();
  await act(async () => { old.frame('code', { code: 'late old content', filepath: 'shared.py' }); old.frame('done'); old.end(); await oldTurn; });
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === id)).toEqual(before);
  if (state === 'empty' || state === 'partial') await act(async () => { fresh.frame('done'); fresh.end(); await newTurn; });
});

it.each(['partial', 'complete', 'held'] as const)('work lifetime: a late discovered path cannot take a successor destination (%s)', async (state) => {
  const first = mountChat();
  let oldTurn!: Promise<void>;
  act(() => { oldTurn = submitChat(first.result.current, 'Create guessed.py'); });
  const old = await streamFor('Create guessed.py');
  const sourceId = getTabStoreSnapshot().tabs[0].id;
  const second = mountChat();
  let newTurn!: Promise<void>;
  act(() => { newTurn = submitChat(second.result.current, 'Create actual.py'); });
  const fresh = await streamFor('Create actual.py');
  await act(async () => { fresh.frame('code_chunk', { code: 'successor snapshot', filepath: 'actual.py' }); });
  if (state !== 'partial') await act(async () => {
    fresh.frame(state === 'complete' ? 'done' : 'human_required', { input: { approvalToken: 'destination-token' } });
    fresh.end(); await newTurn;
  });
  const before = getTabStoreSnapshot().tabs.find(tab => tab.id !== sourceId)!;
  await act(async () => { old.frame('code', { code: 'older discovered snapshot', filepath: 'actual.py' }); old.frame('done'); old.end(); await oldTurn; });
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === before.id)).toEqual(before);
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === sourceId)?.content).toMatchObject({ code: 'older discovered snapshot', filepath: 'actual.py', streaming: false });
  first.unmount();
  if (state === 'partial') {
    await act(async () => { fresh.frame('code_chunk', { code: 'successor final snapshot', filepath: 'actual.py' }); fresh.frame('done'); fresh.end(); await newTurn; });
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === before.id)?.content).toMatchObject({ code: 'successor final snapshot', streaming: false });
  }
});

it.each([false, true].flatMap(existing => ['conversation', 'unmount'].map(next => [existing, next] as const)))(
  'retained destination: a late discovery cannot replace newer work after owner %s / %s', async (existing, next) => {
    if (existing) {
      const seed = mountChat();
      act(() => { submitChat(seed.result.current, 'Create actual.py initial'); });
      const wire = await streamFor('Create actual.py initial');
      await act(async () => { wire.frame('code_chunk', { code: 'initial snapshot', filepath: 'actual.py' }); wire.frame('done'); wire.end(); });
      seed.unmount();
    }
    const first = mountChat();
    let oldTurn!: Promise<void>;
    act(() => { oldTurn = submitChat(first.result.current, 'Create guessed.py delayed'); });
    const old = await streamFor('Create guessed.py delayed');
    const source = getTabStoreSnapshot().tabs.find(tab => tab.content?.filepath === 'guessed.py')!;
    const second = mountChat();
    let newTurn!: Promise<void>;
    act(() => { newTurn = submitChat(second.result.current, 'Create actual.py newer'); });
    const fresh = await streamFor('Create actual.py newer');
    await act(async () => { fresh.frame('code_chunk', { code: 'newer retained snapshot', filepath: 'actual.py' }); fresh.frame('done'); fresh.end(); await newTurn; });
    const before = getTabStoreSnapshot().tabs.find(tab => tab.id !== source.id && tab.content?.filepath === 'actual.py')!;
    expect(before.content).toMatchObject({ code: 'newer retained snapshot', streaming: false });
    if (next === 'unmount') second.unmount();
    else {
      act(() => { submitChat(second.result.current, 'Explain the retained result'); });
      await streamFor('Explain the retained result');
    }
    await act(async () => { old.frame('code', { code: 'stale discovered snapshot', filepath: 'actual.py' }); old.frame('done'); old.end(); await oldTurn; });
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === before.id)).toEqual(before);
    expect(getTabStoreSnapshot().tabs.find(tab => tab.id === source.id)?.content).toMatchObject({ code: 'stale discovered snapshot', filepath: 'actual.py', streaming: false });
  },
);

it('retained destination: a late discovery can still reuse an unchanged result known at submission', async () => {
  const seed = mountChat();
  let initial!: Promise<void>;
  act(() => { initial = submitChat(seed.result.current, 'Create actual.py established'); });
  const wire = await streamFor('Create actual.py established');
  await act(async () => { wire.frame('code_chunk', { code: 'established snapshot', filepath: 'actual.py' }); wire.frame('done'); wire.end(); await initial; });
  const id = getTabStoreSnapshot().tabs.find(tab => tab.content?.filepath === 'actual.py')!.id;
  seed.unmount();
  const owner = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(owner.result.current, 'Create guessed.py update'); });
  const update = await streamFor('Create guessed.py update');
  await act(async () => { update.frame('code', { code: 'intentional updated snapshot', filepath: 'actual.py' }); update.frame('done'); update.end(); await turn; });
  expect(getTabStoreSnapshot().tabs.find(tab => tab.id === id)?.content).toMatchObject({ code: 'intentional updated snapshot', streaming: false });
});

it('chat cleanup: settles an unfinished turn before resetting stores and restoring transport', async () => {
  const { result } = mountChat();
  let turn!: Promise<void>;
  act(() => { turn = submitChat(result.current, 'Explain a cleanup case'); });
  const stream = await streamFor('Explain a cleanup case');
  await act(async () => { stream.frame('text_chunk', { text: 'Partial before a failed assertion' }); });
  expect(getConversationPhase()).toBe('streaming');
  const escaped: string[] = [];
  // Both old and future transports are local fakes even during RED. Exercise
  // the assertion-failure cleanup path without ever restoring real network.
  await act(async () => {
    await finishChatTest(() => vi.stubGlobal('fetch', async (url: string) => {
      escaped.push(String(url));
      return new Response('{}', { status: 503 });
    }));
    await turn;
  });
  expect(escaped).toEqual([]);
  expect(getConversationPhase()).toBe('idle');
});
