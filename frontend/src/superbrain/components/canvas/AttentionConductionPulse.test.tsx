import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const useFrameMock = vi.hoisted(() => vi.fn());

vi.mock('@react-three/fiber', () => ({
  useFrame: useFrameMock,
}));

import AttentionConductionPulse from './AttentionConductionPulse';

describe('AttentionConductionPulse', () => {
  beforeEach(() => {
    useFrameMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders nothing when there is no attention transfer', () => {
    const { container } = render(
      <AttentionConductionPulse tabs={[]} attention={null} reducedMotion={false} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('does not register a frame callback when there is no path to animate', () => {
    render(<AttentionConductionPulse tabs={[]} attention={null} reducedMotion />);

    expect(useFrameMock).not.toHaveBeenCalled();
  });

  it('stays empty across re-renders with reduced motion toggled', () => {
    const { container, rerender } = render(
      <AttentionConductionPulse tabs={[]} attention={null} reducedMotion={false} />,
    );
    rerender(<AttentionConductionPulse tabs={[]} attention={null} reducedMotion />);

    expect(container).toBeEmptyDOMElement();
    expect(useFrameMock).not.toHaveBeenCalled();
  });
});
