import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import IdentityReadout from './IdentityReadout';

const mocks = vi.hoisted(() => ({
  subscribeCognition: vi.fn(),
  setActiveBrain: vi.fn(),
  subscribeActiveBrain: vi.fn(),
  getActiveBrain: vi.fn(),
  unsubscribeCognition: vi.fn(),
  unsubscribeBrain: vi.fn(),
}));

vi.mock('@react-three/drei', () => ({
  Text: ({ children }: { children?: React.ReactNode }) => <span data-testid="text">{children}</span>,
}));

vi.mock('@react-three/fiber', () => ({
  useFrame: () => {},
}));

vi.mock('@/lib/cognitionBus', () => ({
  subscribeCognition: mocks.subscribeCognition,
}));

vi.mock('@/lib/activeBrain', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    getActiveBrain: mocks.getActiveBrain,
    setActiveBrain: mocks.setActiveBrain,
    subscribeActiveBrain: mocks.subscribeActiveBrain,
  };
});

type CognitionEvent = { type: string; data?: Record<string, unknown> };

function lastCognitionHandler(): (event: CognitionEvent) => void {
  const calls = mocks.subscribeCognition.mock.calls;
  return calls[calls.length - 1][0] as (event: CognitionEvent) => void;
}

describe('IdentityReadout', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    mocks.getActiveBrain.mockReturnValue({ provider: 'local', model: 'm1' });
    mocks.subscribeCognition.mockReturnValue(mocks.unsubscribeCognition);
    mocks.subscribeActiveBrain.mockReturnValue(mocks.unsubscribeBrain);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    mocks.subscribeCognition.mockReset();
    mocks.setActiveBrain.mockReset();
    mocks.subscribeActiveBrain.mockReset();
    mocks.getActiveBrain.mockReset();
    mocks.unsubscribeCognition.mockReset();
    mocks.unsubscribeBrain.mockReset();
  });

  it('shows the default name and supervised label', () => {
    render(<IdentityReadout />);
    expect(screen.getByText('GAGOS')).toBeInTheDocument();
    expect(screen.getByText('supervised')).toBeInTheDocument();
  });

  it('uses a custom name and hides the supervised label when unsupervised', () => {
    render(<IdentityReadout name="Aria" supervised={false} />);
    expect(screen.getByText('Aria')).toBeInTheDocument();
    expect(screen.queryByText('GAGOS')).toBeNull();
    expect(screen.queryByText('supervised')).toBeNull();
  });

  it('forwards route events to setActiveBrain with the mapped fields', () => {
    render(<IdentityReadout />);
    const handler = lastCognitionHandler();

    act(() => {
      handler({
        type: 'route',
        data: {
          provider: 'bedrock',
          model: 'kimi',
          privacy: 'cloud',
          turn_id: 't-7',
          mode: 'chat',
          extra: 'ignored',
        },
      });
    });

    expect(mocks.setActiveBrain).toHaveBeenCalledTimes(1);
    expect(mocks.setActiveBrain).toHaveBeenCalledWith({
      provider: 'bedrock',
      model: 'kimi',
      privacy: 'cloud',
      turn_id: 't-7',
      mode: 'chat',
    });
  });

  it('ignores route events without data and other event types', () => {
    render(<IdentityReadout />);
    const handler = lastCognitionHandler();

    act(() => {
      handler({ type: 'route' });
      handler({ type: 'voice-speaking' });
      handler({ type: 'other', data: { provider: 'x' } });
    });

    expect(mocks.setActiveBrain).not.toHaveBeenCalled();
  });

  it('re-reads the active brain when the brain subscription fires', () => {
    render(<IdentityReadout />);
    const initialReads = mocks.getActiveBrain.mock.calls.length;
    expect(initialReads).toBeGreaterThanOrEqual(1);

    const listener = mocks.subscribeActiveBrain.mock.calls[0][0] as () => void;
    act(() => {
      listener();
    });

    expect(mocks.getActiveBrain.mock.calls.length).toBe(initialReads + 1);
  });

  it('unsubscribes from both sources on unmount', () => {
    const { unmount } = render(<IdentityReadout />);
    expect(mocks.unsubscribeCognition).not.toHaveBeenCalled();
    expect(mocks.unsubscribeBrain).not.toHaveBeenCalled();

    unmount();

    expect(mocks.unsubscribeCognition).toHaveBeenCalledTimes(1);
    expect(mocks.unsubscribeBrain).toHaveBeenCalledTimes(1);
  });
});
