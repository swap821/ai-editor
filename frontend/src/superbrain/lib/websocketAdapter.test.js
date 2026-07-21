import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { WebSocketAdapter } from './websocketAdapter';

describe('WebSocketAdapter', () => {
  let wsMock;
  
  beforeEach(() => {
    wsMock = {
      close: vi.fn(),
    };
    global.WebSocket = class {
      constructor(url) {
        this.url = url;
        global.lastWsInstance = this; // Save it globally for the test to access
      }
      close() { wsMock.close(); }
    };
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('connects to websocket', () => {
    const adapter = new WebSocketAdapter('/api/ws');
    adapter.connect();
    
    expect(adapter.socket.url).toContain('ws://localhost:3000/api/ws');
    
    global.lastWsInstance.onopen();
    expect(adapter.connected).toBe(true);
  });

  it('handles messages and notifies subscribers', () => {
    const adapter = new WebSocketAdapter('/api/ws');
    adapter.connect();
    
    const listener = vi.fn();
    adapter.subscribe(listener);
    
    global.lastWsInstance.onmessage({ data: JSON.stringify({ type: 'test' }) });
    expect(listener).toHaveBeenCalledWith({ type: 'test' });
  });

  it('reconnects on close', () => {
    const adapter = new WebSocketAdapter('/api/ws');
    adapter.connect();
    
    global.lastWsInstance.onclose();
    expect(adapter.connected).toBe(false);
    expect(adapter.socket).toBeNull();
    
    vi.advanceTimersByTime(2500); // 1000 * Math.pow(2, 1) = 2000
    
    // Should have reconnected, creating a new socket
    expect(adapter.socket).not.toBeNull();
  });
});
