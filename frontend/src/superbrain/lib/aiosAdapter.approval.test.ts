import { beforeEach, describe, expect, it } from 'vitest';
import { getPendingApproval, subscribePendingApproval } from './aiosAdapter';

type Pending = ReturnType<typeof getPendingApproval>;
type InjectFn = (over?: Partial<Record<string, unknown>>) => void;
type ClearFn = () => void;

const host = window as unknown as { __injectApproval?: InjectFn; __clearApproval?: ClearFn };

beforeEach(() => {
  host.__clearApproval?.();
});

describe('approval single source of truth', () => {
  it('starts with no pending approval', () => {
    expect(getPendingApproval()).toBeNull();
  });

  it('subscribePendingApproval emits current state immediately on subscribe', () => {
    host.__injectApproval!({ token: 'late-sub-token', prompt: 'late' });

    const seen: Pending[] = [];
    const unsub = subscribePendingApproval((p) => seen.push(p));

    expect(seen.length).toBe(1);
    expect(seen[0]?.token).toBe('late-sub-token');
    unsub();
  });

  it('notifies every subscriber when state changes', () => {
    const a: Pending[] = [];
    const b: Pending[] = [];
    const unsubA = subscribePendingApproval((p) => a.push(p));
    const unsubB = subscribePendingApproval((p) => b.push(p));

    expect(a.length).toBe(1);
    expect(b.length).toBe(1);

    host.__injectApproval!({ token: 'multi', prompt: 'multi' });

    expect(a.length).toBe(2);
    expect(b.length).toBe(2);
    expect(a[1]?.token).toBe('multi');
    expect(b[1]?.token).toBe('multi');

    unsubA();
    unsubB();
  });

  it('does not notify a listener after it unsubscribes', () => {
    const seen: Pending[] = [];
    const unsub = subscribePendingApproval((p) => seen.push(p));

    unsub();
    host.__injectApproval!({ token: 'after-unsub' });

    expect(seen.length).toBe(1); // initial emission only
  });

  it('__clearApproval resets persisted truth and notifies subscribers', () => {
    host.__injectApproval!({ token: 'to-clear' });

    const seen: Pending[] = [];
    const unsub = subscribePendingApproval((p) => seen.push(p));

    expect(seen[0]?.token).toBe('to-clear');

    host.__clearApproval!();

    expect(getPendingApproval()).toBeNull();
    expect(seen.length).toBe(2);
    expect(seen[1]).toBeNull();

    unsub();
  });
});
