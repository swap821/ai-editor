import { act, cleanup, fireEvent, render, renderHook, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useWorkMaterialization } from './useWorkMaterialization';
import { LivingWorkspaceShell } from '../../livingMirror/LivingWorkspaceShell';
import { __resetAiosAdapterForTests, getLastEmittedCode, getPendingApproval, sendDirective } from '../../superbrain/lib/aiosAdapter';
import { __resetTabStoreForTests, getTabStoreSnapshot, showContentSurface } from '../../superbrain/lib/tabStore';
import { setConversationPhase } from '../../superbrain/lib/conversationPhaseBus';
import { useMirrorStore } from '../../superbrain/lib/mirrorStore';

type Stream = { frame: (event: string, data?: object) => void; end: () => void };
const streams = new Map<string, Stream>();
const initialMirror = useMirrorStore.getState();

// Only the transport is substituted. The real adapter, SSE parser, request
// ownership, materialization store and readable Shell run together. These
// controlled, deliberately abort-ignoring streams are NOT live-backend evidence.
beforeEach(() => {
  streams.clear();
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  setConversationPhase('idle');
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/api/v1/auth/session')) {
      return new Response(JSON.stringify({ authenticated: true }), { headers: { 'Content-Type': 'application/json' } });
    }
    if (String(url).endsWith('/api/generate')) {
      const text = JSON.parse(String(init?.body)).messages[0].content[0].text as string;
      const body = new ReadableStream<Uint8Array>({ start(controller) {
        streams.set(text, {
          frame: (event, data = {}) => controller.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)),
          end: () => controller.close(),
        });
      } });
      return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
    }
    return new Response('{}', { status: 503, headers: { 'Content-Type': 'application/json' } });
  }));
});
afterEach(() => {
  cleanup();
  __resetAiosAdapterForTests();
  __resetTabStoreForTests();
  useMirrorStore.setState(initialMirror);
  vi.unstubAllGlobals();
});

async function stream(text: string) {
  await waitFor(() => expect(streams.has(text)).toBe(true));
  return streams.get(text)!;
}
function mountWork() {
  const hook = renderHook(() => useWorkMaterialization({ setOnline: () => {}, setMilestones: () => {}, chatModelId: 'auto' }));
  render(<LivingWorkspaceShell experienceMode="expert" />);
  return hook;
}

it('returns each request’s own final code when streams interleave', async () => {
  const first = sendDirective('first request');
  const second = sendDirective('second request');
  const a = await stream('first request');
  const b = await stream('second request');
  a.frame('code_chunk', { code: 'partial a', language: 'python', filepath: 'a/one.py' });
  b.frame('code', { code: 'final b', language: 'typescript', filepath: 'b/two.ts' });
  b.frame('done'); b.end();
  const bResult = await second;
  a.frame('code', { code: 'final a', language: 'python', filepath: 'a/one.py' });
  a.frame('done'); a.end();
  const aResult = await first;
  expect(bResult).toMatchObject({ emittedCode: { code: 'final b', language: 'typescript', filepath: 'b/two.ts' } });
  expect(aResult).toMatchObject({ emittedCode: { code: 'final a', language: 'python', filepath: 'a/one.py' } });
});

it('does not admit buffered code or approval frames after local abort', async () => {
  const abort = new AbortController();
  const previous = getLastEmittedCode();
  const turn = sendDirective('cancelled request', abort.signal).catch((error: Error) => error);
  const old = await stream('cancelled request');
  abort.abort();
  old.frame('code', { code: 'foreign code', filepath: 'wrong.py' });
  old.frame('human_required', { input: { approvalToken: 'stale-token' } });
  old.frame('done'); old.end();
  expect(await turn).toMatchObject({ name: 'AbortError' });
  expect(getLastEmittedCode()).toBe(previous);
  expect(getPendingApproval()).toBeNull();
});

it.each([false, true])('a foreign stream cannot supply current work (own fenced answer: %s)', async (hasOwnAnswer) => {
  const { result: work } = mountWork();
  let current!: Promise<void>;
  act(() => { current = work.current.submit('create current.py'); });
  const own = await stream('create current.py');
  const foreignTurn = sendDirective('foreign request');
  const foreign = await stream('foreign request');
  foreign.frame('code', { code: 'print("foreign")', language: 'python', filepath: 'foreign.py' });
  foreign.frame('done'); foreign.end();
  await act(async () => { await foreignTurn; });
  await act(async () => {
    if (hasOwnAnswer) own.frame('text_chunk', { text: '```python\nprint("own")\n```' });
    own.frame('done'); own.end();
    await current;
  });
  expect(screen.queryByText('print("foreign")')).not.toBeInTheDocument();
  const tab = getTabStoreSnapshot().tabs[0];
  if (hasOwnAnswer) {
    expect(screen.getByText('print("own")')).toBeVisible();
    expect(tab.content).toMatchObject({ code: 'print("own")', filepath: 'current.py', streaming: false });
  } else {
    expect(tab.content?.code).toBe('');
    expect(tab.lifecycle).toBe('retracting');
  }
});

it('keeps the same streaming reader and full originating path at final-code settlement', async () => {
  const { result: work } = mountWork();
  let turn!: Promise<void>;
  act(() => { turn = work.current.submit('create item.py'); });
  const own = await stream('create item.py');
  const id = getTabStoreSnapshot().tabs[0].id;
  await act(async () => own.frame('code_chunk', { code: 'print("draft")', language: 'python', filepath: 'src/item.py' }));
  const reader = await screen.findByText('print("draft")');
  reader.scrollTop = 29;
  await act(async () => {
    own.frame('code', { code: 'print("final")', language: 'python', filepath: 'src/item.py' });
    own.frame('done'); own.end();
    await turn;
  });
  expect(screen.getByText('print("final")')).toBe(reader);
  expect(reader.scrollTop).toBe(29);
  expect(getTabStoreSnapshot().tabs[0]).toMatchObject({ id, content: { filepath: 'src/item.py', code: 'print("final")', streaming: false } });
});

it('retains request-owned code after EOF without inventing a terminal success', async () => {
  const turn = sendDirective('interrupted request');
  const own = await stream('interrupted request');
  own.frame('code_chunk', { code: 'partial', language: 'python', filepath: 'partial.py' });
  own.end();
  expect(await turn).toMatchObject({ ok: false, paused: false, emittedCode: { code: 'partial', filepath: 'partial.py' } });
});

it('late buffered code after Cancel cannot overwrite the retained partial or the next reader', async () => {
  const { result: work } = mountWork();
  let previous!: Promise<void>;
  act(() => { previous = work.current.submit('create previous.py'); });
  const old = await stream('create previous.py');
  await act(async () => old.frame('code_chunk', { code: 'print("partial old")', language: 'python', filepath: 'previous.py' }));
  const retainedReader = await screen.findByText('print("partial old")');
  act(() => work.current.stopTurn());
  let current!: Promise<void>;
  act(() => { current = work.current.submit('create next.py'); });
  const own = await stream('create next.py');
  await act(async () => {
    old.frame('code', { code: 'print("late old")', language: 'python', filepath: 'next.py' });
    old.frame('done'); old.end();
    await previous;
    own.frame('code', { code: 'print("next")', language: 'python', filepath: 'next.py' });
    own.frame('done'); own.end();
    await current;
  });
  expect(screen.getByText('print("partial old")')).toBe(retainedReader);
  expect(screen.queryByText('print("late old")')).not.toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('complementary', { name: 'Spinal workspace anchors' })).getByRole('button', { name: 'next.py' }));
  expect(screen.getByText('print("next")')).toBeVisible();
  expect(getTabStoreSnapshot().tabs.find((tab) => tab.content?.filepath === 'previous.py')?.content?.completion).toBe('cancelled');
});

it('does not overwrite another full path merely because its basename matches', async () => {
  const { result: work } = mountWork();
  let otherId!: string;
  act(() => { otherId = showContentSurface({ code: 'print("other path")', language: 'python', filepath: 'other/item.py' }).id; });
  let turn!: Promise<void>;
  act(() => { turn = work.current.submit('create item.py'); });
  const own = await stream('create item.py');
  const writingId = getTabStoreSnapshot().tabs.find((tab) => tab.id !== otherId)!.id;
  await act(async () => {
    own.frame('code', { code: 'print("current path")', language: 'python', filepath: 'src/item.py' });
    own.frame('done'); own.end();
    await turn;
  });
  const snapshot = getTabStoreSnapshot();
  expect(snapshot.tabs.find((tab) => tab.id === otherId)).toMatchObject({ content: { code: 'print("other path")', filepath: 'other/item.py' } });
  expect(snapshot.tabs.find((tab) => tab.id === writingId)).toMatchObject({ content: { code: 'print("current path")', filepath: 'src/item.py', streaming: false } });
});

it.each(['cancel', 'EOF'])('preserves an admitted path through mixed text/code frames and %s', async (ending) => {
  const { result: work } = mountWork();
  let turn!: Promise<void>;
  act(() => { turn = work.current.submit('create item.py'); });
  const own = await stream('create item.py');
  await act(async () => own.frame('code_chunk', { code: 'print("first")', language: 'python', filepath: 'src/item.py' }));
  await screen.findByText('print("first")');
  await act(async () => own.frame('text_chunk', { text: '```python\nprint("mixed")' }));
  await screen.findByText('print("mixed")');
  const mixedPath = getTabStoreSnapshot().tabs[0].content?.filepath;
  if (ending === 'cancel') act(() => work.current.stopTurn());
  await act(async () => { own.end(); await turn; });
  expect(mixedPath).toBe('src/item.py');
  expect(getTabStoreSnapshot().tabs[0].content).toMatchObject({ filepath: 'src/item.py', streaming: false, completion: ending === 'cancel' ? 'cancelled' : 'incomplete' });
});

it('keeps the request’s admitted path when subsequent code frames omit it', async () => {
  const { result: work } = mountWork();
  let turn!: Promise<void>;
  act(() => { turn = work.current.submit('create item.py'); });
  const own = await stream('create item.py');
  await act(async () => own.frame('code_chunk', { code: 'print("first")', language: 'python', filepath: 'src/item.py' }));
  await screen.findByText('print("first")');
  await act(async () => own.frame('code_chunk', { code: 'print("second")', language: 'python' }));
  await screen.findByText('print("second")');
  const streamedPath = getTabStoreSnapshot().tabs[0].content?.filepath;
  await act(async () => {
    own.frame('code', { code: 'print("final")', language: 'python' });
    own.frame('done'); own.end(); await turn;
  });
  expect(streamedPath).toBe('src/item.py');
  expect(getTabStoreSnapshot().tabs[0].content).toMatchObject({ filepath: 'src/item.py', code: 'print("final")', streaming: false });
});

it('the final request snapshot preserves an already admitted path omitted by later code frames', async () => {
  const turn = sendDirective('path metadata request');
  const own = await stream('path metadata request');
  own.frame('code_chunk', { code: 'first', language: 'python', filepath: 'src/item.py' });
  own.frame('code', { code: 'final', language: 'python' });
  own.frame('done'); own.end();
  expect(await turn).toMatchObject({ emittedCode: { code: 'final', language: 'python', filepath: 'src/item.py' } });
});
