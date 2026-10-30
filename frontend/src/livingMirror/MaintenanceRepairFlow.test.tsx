import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MaintenanceRepairFlow } from './MaintenanceRepairFlow';

const DIFF = "--- a/frontend/src/workbench/Panel.jsx\n+++ b/frontend/src/workbench/Panel.jsx\n-import { useState, useMemo } from 'react';\n+import { useMemo } from 'react';\n";

type Call = { url: string; method: string; body: unknown };

function backend(responses: Record<string, { status?: number; body: unknown }>, calls: Call[]) {
  return vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? 'GET';
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    const key = `${method} ${url.replace(/^.*\/api\//, '/api/')}`;
    const match = Object.entries(responses).find(([pattern]) => key === pattern || key.startsWith(pattern));
    if (!match) throw new Error(`unexpected request ${key}`);
    const { status = 200, body } = match[1];
    return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);
  });
}

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('MaintenanceRepairFlow', () => {
  it('shows the exact diff and allows nothing until the operator has read it', async () => {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend({ 'GET /api/v1/maintenance/findings/fp-1/preview': { body: { diff: DIFF, current: true, operation_id: 'REMOVE_UNUSED_FRONTEND_IMPORTS_V1' } } }, calls));
    render(<MaintenanceRepairFlow fingerprint="fp-1" available refresh={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview the repair' }));
    expect((await screen.findByLabelText('Repair diff')).textContent).toContain("+import { useMemo } from 'react';");
    const prepare = screen.getByRole('button', { name: 'Prepare the repair' });
    expect(prepare).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'I read this exact change.' }));
    expect(prepare).not.toBeDisabled();
  });

  it('refuses to prepare a repair whose file changed since the scan', async () => {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend({ 'GET /api/v1/maintenance/findings/fp-1/preview': { body: { diff: DIFF, current: false, operation_id: 'X' } } }, calls));
    render(<MaintenanceRepairFlow fingerprint="fp-1" available refresh={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview the repair' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Scan again before repairing');
    expect(screen.getByRole('checkbox', { name: 'I read this exact change.' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Prepare the repair' })).toBeDisabled();
  });

  it('prepares, approves the exact contract it was given, and runs, each as its own step', async () => {
    const calls: Call[] = [];
    const refresh = vi.fn();
    vi.stubGlobal('fetch', backend({
      'GET /api/v1/maintenance/findings/fp-1/preview': { body: { diff: DIFF, current: true, operation_id: 'REMOVE_UNUSED_FRONTEND_IMPORTS_V1' } },
      'POST /api/v1/maintenance/repairs/missions': { body: { mission_id: 'maint-1', state: 'draft', contract_digest: 'digest-1' } },
      'POST /api/v1/maintenance/repairs/maint-1/approve': { body: { mission_id: 'maint-1', state: 'approved', contract_digest: 'digest-1' } },
      'POST /api/v1/maintenance/repairs/run': { body: { status: 'VERIFIED_RESOLVED', mission_id: 'maint-1', finding_id: 'f-1', reason: '' } },
    }, calls));
    render(<MaintenanceRepairFlow fingerprint="fp-1" available refresh={refresh} />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview the repair' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'I read this exact change.' }));
    fireEvent.click(screen.getByRole('button', { name: 'Prepare the repair' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve the repair' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Run the approved repair' }));
    expect(await screen.findByText(/Repair finished: VERIFIED_RESOLVED/)).toBeInTheDocument();
    const posts = calls.filter((call) => call.method === 'POST');
    expect(posts.map((call) => call.url.replace(/^.*\/api\//, '/api/'))).toEqual([
      '/api/v1/maintenance/repairs/missions',
      '/api/v1/maintenance/repairs/maint-1/approve',
      '/api/v1/maintenance/repairs/run',
    ]);
    expect(posts[0].body).toEqual({ finding_fingerprint: 'fp-1' });
    expect(posts[1].body).toEqual({ contract_digest: 'digest-1' });
    expect(posts[2].body).toEqual({ mission_id: 'maint-1' });
    expect(refresh).toHaveBeenCalled();
  });

  it('says how to recover when approval needs a fresh re-authentication', async () => {
    const calls: Call[] = [];
    vi.stubGlobal('fetch', backend({
      'GET /api/v1/maintenance/findings/fp-1/preview': { body: { diff: DIFF, current: true, operation_id: 'X' } },
      'POST /api/v1/maintenance/repairs/missions': { body: { mission_id: 'maint-1', state: 'draft', contract_digest: 'digest-1' } },
      'POST /api/v1/maintenance/repairs/maint-1/approve': { status: 403, body: { detail: 'privileged session required' } },
    }, calls));
    render(<MaintenanceRepairFlow fingerprint="fp-1" available refresh={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: 'Preview the repair' }));
    fireEvent.click(await screen.findByRole('checkbox', { name: 'I read this exact change.' }));
    fireEvent.click(screen.getByRole('button', { name: 'Prepare the repair' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Approve the repair' }));
    expect(await screen.findByText(/re-authenticate in the Sovereign Bond panel/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Run the approved repair' })).toBeNull();
  });
});
