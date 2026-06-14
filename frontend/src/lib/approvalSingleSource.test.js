import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  __resetAiosAdapterForTests,
  approvePendingApproval,
  getPendingApproval,
  sendDirective,
  subscribePendingApproval,
} from '../superbrain/lib/aiosAdapter';

/* P0-3 — the approval gate is the supervised-Jarvis trust contract, so it must
   be driven by the PERSISTED adapter truth, never by a fire-and-forget bus event
   that can be missed (which would leave a real pause showing the hold text but no
   AUTHORIZE/REJECT — a hung run). These tests pin the invariants the HUD's
   subscription relies on:
     1. a paused turn ALWAYS leaves getPendingApproval() populated, and
     2. subscribePendingApproval delivers the CURRENT truth immediately on
        subscribe (so a late mount / missed event still becomes actionable) and
        again on every change.
   The adapter is generated from the lab via `npm run port`; importing it here
   enforces the contract in CI regardless of the port. */

function sseResponse(frames) {
  const text = frames
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('');
  const bytes = new TextEncoder().encode(text);
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start(controller) {
        controller.enqueue(bytes);
        controller.close();
      },
    }),
  };
}

const PAUSE_FRAMES = [
  ['step', { type: 'tool_call', tool: 'create_file', id: 'c-0' }],
  [
    'human_required',
    {
      text: 'Approval required to create training_ground/x.py',
      input: {
        approvalToken: 'tok-123',
        creations: [{ filepath: 'training_ground/x.py', content: 'print(1)\n' }],
      },
    },
  ],
];

describe('P0-3 approval single source of truth', () => {
  beforeEach(() => {
    __resetAiosAdapterForTests();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a paused turn leaves the persisted approval populated (paused <=> getPendingApproval)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(PAUSE_FRAMES)));
    const result = await sendDirective('write the file');
    expect(result.paused).toBe(true);
    const pending = getPendingApproval();
    expect(pending).not.toBeNull();
    expect(pending?.token).toBe('tok-123');
    expect(pending?.kind).toBe('create');
    expect(pending?.filepath).toBe('training_ground/x.py');
  });

  it('a listener subscribing AFTER the pause still receives the current approval (missed-event safety)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(PAUSE_FRAMES)));
    await sendDirective('write the file');
    // A HUD that mounted AFTER the transient 'approval-required' event already
    // fired must still be handed the live approval — this is the core guarantee.
    const seen = [];
    const unsub = subscribePendingApproval((p) => seen.push(p));
    expect(seen).toHaveLength(1);
    expect(seen[0]?.token).toBe('tok-123');
    unsub();
  });

  it('notifies a pre-subscribed listener on pause and clears it on approve', async () => {
    const seen = [];
    const unsub = subscribePendingApproval((p) => seen.push(p));
    expect(seen[seen.length - 1]).toBeNull(); // immediate delivery of current (none)

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(PAUSE_FRAMES)));
    await sendDirective('write the file');
    expect(seen[seen.length - 1]?.token).toBe('tok-123'); // pause -> actionable

    // Approve replays the turn; mock the replay as a clean completion.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([['done', {}]])));
    await approvePendingApproval();
    expect(seen[seen.length - 1]).toBeNull(); // resolved -> panel stands down
    expect(getPendingApproval()).toBeNull();
    unsub();
  });
});
