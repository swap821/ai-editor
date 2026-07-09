import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SettingsPanel from './SettingsPanel';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('SettingsPanel', () => {
  it('renders correctly', () => {
    render(<SettingsPanel onClose={vi.fn()} />);
    
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText('System Preferences')).toBeInTheDocument();
    expect(screen.getByText('Ollama')).toBeInTheDocument();
    expect(screen.getByText('Bedrock')).toBeInTheDocument();
    expect(screen.getByText('Gemini')).toBeInTheDocument();
  });

  it('toggles autonomy', () => {
    render(<SettingsPanel onClose={vi.fn()} />);
    
    expect(screen.getByText('ENABLED (YELLOW allowed)')).toBeInTheDocument();
    
    // The checkbox is hidden, but we can click the label text
    fireEvent.click(screen.getByText('ENABLED (YELLOW allowed)'));
    
    expect(screen.getByText('DISABLED (GREEN only)')).toBeInTheDocument();
  });
});
