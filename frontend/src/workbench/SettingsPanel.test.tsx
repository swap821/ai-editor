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
    render(<SettingsPanel onClose={onCloseMock} />);
    expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    expect(screen.getByText('Earned Autonomy')).toBeInTheDocument();
  });

  it('saves config and closes', async () => {
    render(<SettingsPanel onClose={onCloseMock} />);
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    const btn = screen.getByText('Apply & Close');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/system/config'),
        expect.objectContaining({ method: 'POST' })
      );
    });

    expect(onCloseMock).toHaveBeenCalled();
  });

  it('triggers restart', async () => {
    window.confirm = vi.fn(() => true);
    window.alert = vi.fn();
    
    render(<SettingsPanel onClose={onCloseMock} />);
    
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    const btn = screen.getByText('Restart Backend');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/system/restart'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });
});
