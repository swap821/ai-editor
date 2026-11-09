// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, within } from '@testing-library/react';
import IntelligenceHiringPanel from './IntelligenceHiringPanel';
import { useResource } from '../livingMirror/resource';
import { durableCollection } from '../livingMirror/recordCollections';

vi.mock('../livingMirror/resource', () => ({ useResource: vi.fn() }));

vi.mock('../livingMirror/ResourceNotice', () => ({
  ResourceNotice: ({ resource, empty }) => (
    <div data-testid="notice" data-status={resource.status}>{empty}</div>
  ),
}));

vi.mock('../livingMirror/recordCollections', () => ({
  durableCollection: vi.fn(() => 'parsed-marker'),
  noRecords: 'no-records-marker',
  textValue: (value) => (value === null || value === undefined || value === '' ? 'n/a' : String(value)),
}));

const fullRecord = {
  request_id: 'req-1',
  purpose: 'Hire analyst',
  status: 'approved',
  mission_id: 'mission-7',
  selected_provider: 'provider-a',
  selected_model: 'model-x',
  data_classification: 'internal',
  external_data_scope: 'none',
  reason: 'lowest cost within boundary',
  redactions: 'ssn',
};

describe('IntelligenceHiringPanel', () => {
  beforeEach(() => {
    vi.mocked(useResource).mockReturnValue({ status: 'ready', data: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the heading and passes the empty message and resource to the notice', () => {
    render(<IntelligenceHiringPanel />);

    expect(screen.getByRole('heading', { name: 'Intelligence routing & hiring' })).toBeTruthy();
    const notice = screen.getByTestId('notice');
    expect(notice.textContent).toBe('No hiring decisions are recorded in the durable repository.');
    expect(notice.getAttribute('data-status')).toBe('ready');
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });

  it('renders each decision with its labelled fields', () => {
    vi.mocked(useResource).mockReturnValue({ status: 'ready', data: [fullRecord] });
    render(<IntelligenceHiringPanel />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(1);
    const item = within(items[0]);
    expect(item.getByText('Hire analyst')).toBeTruthy();
    expect(item.getByText('req-1').tagName).toBe('CODE');
    expect(item.getByText(/approved/)).toBeTruthy();
    expect(item.getByText('Provider-call provenance')).toBeTruthy();

    const expected = {
      Mission: 'mission-7',
      'Selected provider': 'provider-a',
      'Selected model': 'model-x',
      'Data classification': 'internal',
      'Permitted external context': 'none',
      Reason: 'lowest cost within boundary',
      Redactions: 'ssn',
    };
    for (const [label, value] of Object.entries(expected)) {
      const term = item.getByText(label);
      expect(term.tagName).toBe('DT');
      expect(term.nextElementSibling.textContent).toBe(value);
    }
  });

  it('renders one item per record and falls back for missing values', () => {
    vi.mocked(useResource).mockReturnValue({
      status: 'ready',
      data: [fullRecord, { request_id: 'req-2', purpose: 'Sparse request' }],
    });
    render(<IntelligenceHiringPanel />);

    const items = screen.getAllByRole('listitem');
    expect(items).toHaveLength(2);
    const second = within(items[1]);
    expect(second.getByText('Sparse request')).toBeTruthy();
    expect(second.getByText('Mission').nextElementSibling.textContent).toBe('n/a');
    expect(second.getByText('Reason').nextElementSibling.textContent).toBe('n/a');
  });

  it('registers a parser keyed by request_id with the empty fallback', () => {
    render(<IntelligenceHiringPanel />);

    const [, parse, fallback] = vi.mocked(useResource).mock.calls[0];
    expect(fallback).toBe('no-records-marker');
    expect(parse({ some: 'payload' })).toBe('parsed-marker');
    expect(durableCollection).toHaveBeenCalledWith({ some: 'payload' }, 'request_id');
  });
});
