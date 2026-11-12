import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import SovereignStatePanel from './SovereignStatePanel';

vi.mock('../config', () => ({
  API_BASE: 'http://api.test',
  API_HEADERS: {},
}));

const READ_COUNT = 13;

function baseBodies() {
  return [
    {
      enabled: true,
      min_successes: 3,
      entries: [
        {
          signature: 'write:file',
          status: 'earned',
          action_type: 'write_file',
          target_shape: 'src',
          streak: 4,
          success_count: 4,
          failure_count: 0,
        },
        {
          signature: 'delete:dir',
          status: 'revoked',
          action_type: 'delete_dir',
          target_shape: 'tmp',
          streak: 0,
          success_count: 1,
          failure_count: 2,
        },
      ],
    },
    { proposals: [{ id: 7, subject: 'Alice', predicate: 'knows', object: 'Bob' }] },
    { trails: [], summary: { verified: 2, candidate: 1 } },
    { proposals: [{ fingerprint: 'fp-1', skill_name: 'Parsing', level: 2, prompt: 'Parse a thing' }] },
    { lastScan: null, activation: 'manual', localOnly: true },
    { mode: 'normal', cloud_allowed: false },
    { lastRun: null },
    { pheromones: [] },
    { missions: [] },
    { proposals: [] },
    { localOnly: true, authority: 'advisory' },
    {},
    {},
  ];
}

// The panel issues its 13 reads in a fixed order; bodies are matched by that order.
function installFetch(bodies) {
  let readIndex = 0;
  const fetchMock = vi.fn(async (url, init) => {
    if (init && init.method === 'POST') {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    const body = bodies[readIndex % READ_COUNT];
    readIndex += 1;
    if (body instanceof Error) throw body;
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SovereignStatePanel', () => {
  it('shows the offline message when every read fails', async () => {
    installFetch(Array.from({ length: READ_COUNT }, () => new Error('down')));
    render(<SovereignStatePanel />);

    expect(await screen.findByText('Sovereign state link offline')).toBeTruthy();
    expect(screen.queryByLabelText('Earned autonomy ledger')).toBeNull();
  });

  it('renders loaded ledger, facts, resource posture and pending count', async () => {
    installFetch(baseBodies());
    render(<SovereignStatePanel />);

    expect(await screen.findByText('armed · floor 3')).toBeTruthy();
    expect(screen.getByText('Alice — knows — Bob')).toBeTruthy();
    expect(screen.getByText('normal · cloud blocked')).toBeTruthy();
    expect(screen.getByText('2 pending item(s)')).toBeTruthy();
    expect(screen.getByText('2 verified · 1 candidate')).toBeTruthy();
    expect(screen.getByText('No trails yet — experience is still being earned.')).toBeTruthy();
  });

  it('offers Revoke only for non-revoked entries and posts the encoded signature', async () => {
    const fetchMock = installFetch(baseBodies());
    render(<SovereignStatePanel />);

    const ledger = await screen.findByLabelText('Earned autonomy ledger');
    const revokeButtons = within(ledger).getAllByRole('button', { name: 'Revoke' });
    expect(revokeButtons).toHaveLength(1);

    fireEvent.click(revokeButtons[0]);

    await waitFor(() => {
      const posts = fetchMock.mock.calls.filter(([, init]) => init && init.method === 'POST');
      expect(posts).toHaveLength(1);
      expect(posts[0][0]).toEqual(expect.stringContaining('write%3Afile'));
    });
  });

  it('marks only the failed section unavailable when other reads succeed', async () => {
    const bodies = baseBodies();
    bodies[0] = new Error('ledger down');
    installFetch(bodies);
    render(<SovereignStatePanel />);

    expect(await screen.findByText('Autonomy ledger unavailable.')).toBeTruthy();
    expect(screen.queryByText('Sovereign state link offline')).toBeNull();
    expect(screen.getByText('Alice — knows — Bob')).toBeTruthy();
  });
});
