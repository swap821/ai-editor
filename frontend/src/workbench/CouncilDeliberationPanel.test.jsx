import { render, screen, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import CouncilDeliberationPanel from './CouncilDeliberationPanel';
import { subscribeSwarmHUD, resetSwarmHUD } from '../superbrain/lib/swarmHUDStore';

vi.mock('../components/HUDPanel', () => ({
  default: ({ title, children, tint }) => (
    <div data-testid="hud-panel" data-title={title} data-tint={tint}>
      {children}
    </div>
  )
}));

describe('CouncilDeliberationPanel', () => {
  beforeEach(() => {
    resetSwarmHUD();
  });

  it('renders correctly', () => {
    render(<CouncilDeliberationPanel onClose={vi.fn()} />);
    expect(screen.getByTestId('hud-panel')).toBeInTheDocument();
    expect(screen.getByText(/Active Swarm State/i)).toBeInTheDocument();
  });
});
