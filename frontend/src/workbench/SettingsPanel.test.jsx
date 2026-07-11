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
    expect(screen.getByTestId('hud-panel')).toHaveAttribute('data-title', 'System Preferences');
    expect(screen.getByText('Ollama')).toBeInTheDocument();
    expect(screen.getByText('Bedrock')).toBeInTheDocument();
    expect(screen.getByText('Gemini')).toBeInTheDocument();
  });

  it('displays read-only autonomy state', () => {
    render(<SettingsPanel onClose={vi.fn()} />);
    
    expect(screen.getByText('ENABLED (YELLOW allowed)')).toBeInTheDocument();
    
    // The checkbox is disabled, so clicking the label text shouldn't change it
    fireEvent.click(screen.getByText('ENABLED (YELLOW allowed)'));
    
    expect(screen.queryByText('DISABLED (GREEN only)')).not.toBeInTheDocument();
    expect(screen.getByText('ENABLED (YELLOW allowed)')).toBeInTheDocument();
  });
});
