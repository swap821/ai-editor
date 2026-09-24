import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BootstrapReadiness, parseBootstrapReadiness } from './BootstrapReadiness';

const readyPayload = {
  ok: true,
  summary: 'Bootstrap checks passed.',
  checks: [{ name: 'database', passed: true, required: true, message: 'Writable.' }],
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('bootstrap readiness contract', () => {
  it('distinguishes a measured ready response from a blocked response', () => {
    expect(parseBootstrapReadiness(readyPayload)).toMatchObject({ state: 'ready', summary: readyPayload.summary });
    expect(parseBootstrapReadiness({
      ok: false,
      summary: 'Local setup needs attention.',
      checks: [{ name: 'providers', passed: false, required: true, message: 'No model route.' }],
    })).toMatchObject({ state: 'blocked', checks: [{ name: 'providers', passed: false }] });
  });

  it('does not turn a malformed response into a false ready or empty state', () => {
    expect(parseBootstrapReadiness({ ok: true })).toMatchObject({ state: 'unavailable' });
    expect(parseBootstrapReadiness(null)).toMatchObject({ state: 'unavailable' });
  });
});

describe('BootstrapReadiness', () => {
  it('renders measured readiness and sends credentials to the local endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => readyPayload });
    vi.stubGlobal('fetch', fetchMock);

    render(<BootstrapReadiness apiBase="http://localhost:8000" />);

    expect(screen.getByRole('status')).toHaveTextContent('Reading local setup status');
    await waitFor(() => expect(screen.getByText('Local setup is ready.')).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/v1/system/bootstrap',
      expect.objectContaining({ credentials: 'include' }),
    );
  });

  it('shows blocked and unavailable states with recovery guidance', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({
        ok: false,
        summary: 'Provider setup is incomplete.',
        checks: [{ name: 'providers', passed: false, required: true, message: 'Start Ollama or configure a permitted provider.' }],
      }) })
      .mockRejectedValueOnce(new Error('API offline')));

    const view = render(<BootstrapReadiness apiBase="http://localhost:8000" />);
    await waitFor(() => expect(screen.getByText('Setup needs attention.')).toBeInTheDocument());
    expect(screen.getByText('One local setup check needs attention.')).toBeInTheDocument();
    expect(screen.queryByText(/Ollama|provider|model route/i)).not.toBeInTheDocument();

    view.rerender(<BootstrapReadiness apiBase="http://offline:8000" />);
    await waitFor(() => expect(screen.getByText('Setup status is unavailable.')).toBeInTheDocument());
    expect(screen.getByRole('link', { name: 'Recovery guidance' })).toHaveAttribute('href', '#gagos-recovery');
  });
});
