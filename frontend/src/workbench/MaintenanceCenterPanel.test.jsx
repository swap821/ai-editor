import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import MaintenanceCenterPanel from './MaintenanceCenterPanel';

const mocks = vi.hoisted(() => ({
  useResource: vi.fn(),
  sendGuardedCommand: vi.fn(),
}));

vi.mock('../livingMirror/resource', () => ({ useResource: mocks.useResource }));
vi.mock('../livingMirror/ResourceNotice', () => ({
  ResourceNotice: ({ resource, empty }) => (resource.data?.length ? null : <p>{empty}</p>),
}));
vi.mock('../livingMirror/recordCollections', () => ({
  durableCollection: (value) => value,
  noRecords: [],
  textValue: (value) => {
    if (value === null || value === undefined) return '';
    return typeof value === 'string' ? value : JSON.stringify(value);
  },
}));
vi.mock('../livingMirror/commands', () => ({ sendGuardedCommand: mocks.sendGuardedCommand }));

const findingsRefresh = vi.fn();
const scansRefresh = vi.fn();
let calls = 0;
let findingsResource;
let scansResource;

beforeEach(() => {
  vi.clearAllMocks();
  calls = 0;
  findingsResource = { status: 'ready', data: [], refresh: findingsRefresh };
  scansResource = { status: 'ready', data: [], refresh: scansRefresh };
  // The panel asks for findings first, then scans, on every render.
  mocks.useResource.mockImplementation(() => (calls++ % 2 === 0 ? findingsResource : scansResource));
});

describe('MaintenanceCenterPanel', () => {
  it('shows empty notices when nothing is recorded', () => {
    render(<MaintenanceCenterPanel />);

    expect(screen.getByText('No findings are recorded in the durable repository.')).toBeTruthy();
    expect(screen.getByText('No scans are recorded in the durable repository.')).toBeTruthy();
  });

  it('lists findings and scans, and does not offer repair for non-repairable ones', () => {
    findingsResource.data = [
      { finding_id: 'finding-1', kind: 'unused_import', severity: 'low', status: 'RESOLVED', target_id: 'src/a.js', fingerprint: 'fp-1' },
      { finding_id: 'finding-2', kind: 'unused_import', severity: 'low', status: 'OPEN', target_id: 'src/b.js' },
    ];
    scansResource.data = [{ scan_id: 'scan-1', files_scanned: 7 }];

    render(<MaintenanceCenterPanel />);

    expect(screen.getByText('finding-1')).toBeTruthy();
    expect(screen.getByText('finding-2')).toBeTruthy();
    expect(screen.getAllByText('Inspecting this finding does not start a repair.')).toHaveLength(2);
    expect(screen.getByText('scan-1')).toBeTruthy();
    expect(screen.getByText(/"files_scanned": 7/)).toBeTruthy();
  });

  it('reports the finding count and refreshes both lists after an accepted scan', async () => {
    let resolveScan;
    mocks.sendGuardedCommand.mockReturnValue(new Promise((resolve) => { resolveScan = resolve; }));

    render(<MaintenanceCenterPanel />);
    const button = screen.getByRole('button', { name: 'Scan the frontend' });
    fireEvent.click(button);

    expect(await screen.findByText('Scanning…')).toBeTruthy();
    expect(button.disabled).toBe(true);
    expect(mocks.sendGuardedCommand).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ target_id: '.', max_files: 2000, deadline_seconds: 120 }),
      180000,
    );

    resolveScan({ status: 'accepted', data: { finding_count: 3 } });

    expect(await screen.findByText('Frontend scanned: 3 finding(s).')).toBeTruthy();
    await waitFor(() => expect(button.disabled).toBe(false));
    expect(findingsRefresh).toHaveBeenCalledTimes(1);
    expect(scansRefresh).toHaveBeenCalledTimes(1);
  });

  it('handles a missing count and shows the message of a refused scan', async () => {
    mocks.sendGuardedCommand.mockResolvedValueOnce({ status: 'accepted', data: {} });
    render(<MaintenanceCenterPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Scan the frontend' }));
    expect(await screen.findByText('Frontend scanned: an unknown number of finding(s).')).toBeTruthy();

    mocks.sendGuardedCommand.mockResolvedValueOnce({ status: 'rejected', message: 'Scanner is not permitted.' });
    fireEvent.click(screen.getByRole('button', { name: 'Scan the frontend' }));
    expect(await screen.findByText('Scanner is not permitted.')).toBeTruthy();
    expect(screen.queryByText(/Frontend scanned/)).toBeNull();
  });
});
