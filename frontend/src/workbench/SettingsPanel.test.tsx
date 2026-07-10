import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SettingsPanel from './SettingsPanel';

describe('SettingsPanel', () => {
  let fetchMock;
  let onCloseMock;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock;
    onCloseMock = vi.fn();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders settings controls', () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
    render(<SettingsPanel onClose={onCloseMock} />);
    expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    expect(screen.getByText('Earned Autonomy')).toBeInTheDocument();
  });

  it('loads real persisted settings from the backend on mount', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ provider: 'Gemini', autonomy: false, theme: 'Classic' }),
    });

    render(<SettingsPanel onClose={onCloseMock} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/system/config'),
        expect.objectContaining({ credentials: 'include' })
      );
      expect(screen.getByText('DISABLED (GREEN only)')).toBeInTheDocument();
    });
  });

  it('surfaces a load error without crashing when config fetch fails', async () => {
    fetchMock.mockResolvedValueOnce({ ok: false, status: 500, json: async () => ({}) });

    render(<SettingsPanel onClose={onCloseMock} />);

    await waitFor(() => {
      expect(screen.getByText(/Could not load current settings/)).toBeInTheDocument();
    });
    // Defaults are still usable.
    expect(screen.getByText('Ollama')).toBeInTheDocument();
  });

  it('saves config and closes', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) }); // initial load
    render(<SettingsPanel onClose={onCloseMock} />);

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'saved' }) });

    const btn = screen.getByText('Apply & Close');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('/api/v1/system/config'),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ provider: 'Ollama', autonomy: true, theme: 'Superbrain' }),
        })
      );
    });

    expect(onCloseMock).toHaveBeenCalled();
  });

  it('triggers restart with an explicit confirm flag', async () => {
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) }); // initial load
    render(<SettingsPanel onClose={onCloseMock} />);

    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'restarting' }) });

    const btn = screen.getByText('Restart Backend');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining('/api/v1/system/restart'),
        expect.objectContaining({ method: 'POST', body: JSON.stringify({ confirm: true }) })
      );
    });
  });
});
