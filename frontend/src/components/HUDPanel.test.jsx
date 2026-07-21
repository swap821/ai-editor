import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import HUDPanel from './HUDPanel';

// Mock matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

describe('HUDPanel', () => {
  it('renders with title', () => {
    render(<HUDPanel title="Test Panel"><div>Content</div></HUDPanel>);
    expect(screen.getByText('Test Panel')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('minimizes and hides content', () => {
    render(<HUDPanel title="Test Panel"><div>Content</div></HUDPanel>);
    const minimizeBtn = screen.getByLabelText('Minimize');
    fireEvent.click(minimizeBtn);
    // After minimizing, content should not be rendered
    expect(screen.queryByText('Content')).not.toBeInTheDocument();
  });

  it('calls onClose when close button is clicked', () => {
    const handleClose = vi.fn();
    render(<HUDPanel title="Test Panel" onClose={handleClose}><div>Content</div></HUDPanel>);
    const closeBtn = screen.getByLabelText('Close');
    fireEvent.click(closeBtn);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });
});
