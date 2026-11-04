import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import LocalWorkforcePanel from './LocalWorkforcePanel';

const mocks = vi.hoisted(() => ({
  mirror: {},
  resource: {},
  useResource: vi.fn(),
  identifiedRecords: vi.fn(),
  noRecords: vi.fn(),
}));

vi.mock('../superbrain/lib/mirrorStore', () => ({
  useMirrorStore: () => mocks.mirror,
}));

vi.mock('../livingMirror/resource', () => ({
  useResource: mocks.useResource,
}));

vi.mock('../livingMirror/ResourceNotice', () => ({
  ResourceNotice: ({ resource, empty }) => (
    <p>{resource.data?.length ? 'Models available' : empty}</p>
  ),
}));

vi.mock('../livingMirror/recordCollections', () => ({
  identifiedRecords: mocks.identifiedRecords,
  noRecords: mocks.noRecords,
  textValue: (value) => (Array.isArray(value) ? value.join(', ') : String(value ?? '—')),
}));

describe('LocalWorkforcePanel', () => {
  it('renders model details and observed worker records', () => {
    mocks.resource = {
      data: [{
        model_id: 'model-alpha',
        installed: true,
        operator_approved: false,
        health: 'healthy',
        admission_status: 'admitted',
        admission_reason: 'qualified',
        allowed_job_profiles: ['reviewer'],
        expires_at: '2027-01-01',
        limitations: 'local only',
      }],
    };
    mocks.useResource.mockReturnValue(mocks.resource);
    mocks.mirror = {
      observations: { activeWorkers: { status: 'fresh' } },
      activeWorkers: ['worker-alpha', 'worker-beta'],
      workers: { 'worker-alpha': { state: 'busy', missionId: 'mission-1' } },
    };

    render(<LocalWorkforcePanel />);

    expect(screen.getByText('model-alpha')).toBeTruthy();
    expect(screen.getByText('healthy')).toBeTruthy();
    expect(screen.getByText('admitted')).toBeTruthy();
    expect(screen.getByText('reviewer')).toBeTruthy();
    expect(screen.getByText('local only')).toBeTruthy();
    expect(screen.getByText('2 observed active workers · fresh.')).toBeTruthy();
    expect(screen.getByText('busy · mission-1')).toBeTruthy();
    expect(screen.getByText('Active in last snapshot · Mission binding unavailable')).toBeTruthy();

    const [path, parse, fallback] = mocks.useResource.mock.lastCall;
    expect(path).toBe('/api/v1/local-workforce');
    expect(fallback).toBe(mocks.noRecords);
    const records = [{ model_id: 'model-alpha' }];
    parse(records);
    expect(mocks.identifiedRecords).toHaveBeenCalledWith(records, 'model_id');
  });

  it('reports unavailable worker counts and an empty registry', () => {
    mocks.useResource.mockReturnValue({ data: [] });
    mocks.mirror = {
      observations: { activeWorkers: { status: 'unavailable' } },
      activeWorkers: [],
      workers: {},
    };

    render(<LocalWorkforcePanel />);

    expect(screen.getByText('No local models are recorded in the durable registry.')).toBeTruthy();
    expect(screen.getByText('Active worker count unavailable.')).toBeTruthy();
    expect(screen.queryByText(/observed active workers/)).toBeNull();
  });
});
