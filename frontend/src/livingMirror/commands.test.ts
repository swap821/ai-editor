import { afterEach, expect, it, vi } from 'vitest';
import { sendGuardedCommand } from './commands';
const reply = (status: number, body: unknown) => ({ status, ok: status >= 200 && status < 300, json: async () => body }) as Response;
afterEach(() => vi.unstubAllGlobals());
it('consumes the guard challenge using identical body bytes and never returns the token', async () => {
  const body = { missionId: 'm1', contractDigest: 'c1', requestId: 'r1' };
  const fetcher = vi.fn().mockImplementationOnce(async () => {
    body.contractDigest = 'changed-in-ui';
    return reply(428, { detail: { route: '/api/v1/council/approve', approvalToken: 'private-capability' } });
  }).mockResolvedValueOnce(reply(200, { execution: 'scheduled' }));
  vi.stubGlobal('fetch', fetcher);
  const result = await sendGuardedCommand('/api/v1/council/approve', body);
  expect(fetcher.mock.calls[1][1].body).toBe(fetcher.mock.calls[0][1].body);
  expect(fetcher.mock.calls[1][1].headers['X-AIOS-Capability']).toBe('private-capability');
  expect(result.status).toBe('accepted');
  expect(JSON.stringify(result)).not.toContain('private-capability');
});
it('never automatically retries an uncertain mutation', async () => {
  const fetcher = vi.fn().mockRejectedValue(new TypeError('connection lost'));
  vi.stubGlobal('fetch', fetcher);
  expect((await sendGuardedCommand('/api/v1/council/approve', {})).status).toBe('outcome_unknown');
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it('does not manufacture execution from an accepted skill draft', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, { execution: 'mission_service_draft_only', status: 'mission_created' })));
  expect(await sendGuardedCommand('/api/v1/skills/reuse', {})).toMatchObject({ status: 'accepted', data: { execution: 'mission_service_draft_only' } });
});
it('retains an exact rollback continuation privately without exposing its token', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(reply(200, { requiresApproval: true, executed: false, actionType: 'rollback', snapshotId: 's1', approvalToken: 'private-rollback' }))
    .mockResolvedValueOnce(reply(200, { executed: true, result: { restored: true } }));
  vi.stubGlobal('fetch', fetcher);
  const prepared = await sendGuardedCommand('/api/v1/council/missions/m1/rollback', { snapshotId: 's1' });
  expect(JSON.stringify(prepared)).not.toContain('private-rollback');
  expect(fetcher).toHaveBeenCalledTimes(1);
  const result = await prepared.continueRollback!();
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ snapshotId: 's1', approvalToken: 'private-rollback' });
  expect(result.data).toMatchObject({ result: { restored: true } });
});
