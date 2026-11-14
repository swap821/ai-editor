import { afterEach, describe, expect, it, vi } from 'vitest';
import { publishCognition, subscribeCognition } from './cognitionBus';

const unsubscribes: Array<() => void> = [];

afterEach(() => {
  unsubscribes.splice(0).forEach((unsubscribe) => unsubscribe());
});

describe('cognitionBus', () => {
  it('calls subscribers synchronously in subscription order with the published event', () => {
    const received: string[] = [];
    const event = { type: 'knowledge-acquired' as const, label: 'ARCHIVE SHARD' };

    unsubscribes.push(
      subscribeCognition((published) => {
        received.push(`first:${published.label}`);
      }),
      subscribeCognition((published) => {
        received.push(`second:${published.type}`);
      }),
    );

    publishCognition(event);

    expect(received).toEqual(['first:ARCHIVE SHARD', 'second:knowledge-acquired']);
  });

  it('continues notifying later subscribers when an earlier subscriber throws', () => {
    const laterListener = vi.fn();

    unsubscribes.push(
      subscribeCognition(() => {
        throw new Error('listener failed');
      }),
      subscribeCognition(laterListener),
    );

    const event = { type: 'directive' as const, detail: 'begin synthesis' };
    publishCognition(event);

    expect(laterListener).toHaveBeenCalledTimes(1);
    expect(laterListener).toHaveBeenCalledWith(event);
  });

  it('stops notifying a listener after its unsubscribe function is called', () => {
    const listener = vi.fn();
    const stillListening = vi.fn();
    const unsubscribe = subscribeCognition(listener);
    unsubscribes.push(unsubscribe);
    unsubscribes.push(subscribeCognition(stillListening));

    unsubscribe();
    publishCognition({ type: 'burst' });

    expect(listener).not.toHaveBeenCalled();
    expect(stillListening).toHaveBeenCalledTimes(1);
    expect(stillListening).toHaveBeenCalledWith({ type: 'burst' });
  });
});
