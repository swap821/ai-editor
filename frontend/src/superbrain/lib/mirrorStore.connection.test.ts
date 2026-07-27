import { describe, it, expect, beforeEach } from 'vitest';
import { useMirrorStore } from './mirrorStore';

describe('mirrorStore connection state', () => {
  beforeEach(() => {
    useMirrorStore.setState({ status: 'offline', connection: 'disconnected', pendingEvents: 0 });
  });

  it('initializes with disconnected connection state', () => {
    expect(useMirrorStore.getState().connection).toBe('disconnected');
  });

  it('can set connection state to connecting', () => {
    useMirrorStore.getState().setConnection('connecting');
    expect(useMirrorStore.getState().connection).toBe('connecting');
  });

  it('can set connection state to connected', () => {
    useMirrorStore.getState().setConnection('connected');
    expect(useMirrorStore.getState().connection).toBe('connected');
  });
});
