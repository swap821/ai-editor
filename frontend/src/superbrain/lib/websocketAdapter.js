/**
 * websocketAdapter.js
 * Adds fallback layer for SSE connection drops to WebSocket if available.
 */
export class WebSocketAdapter {
  constructor(endpoint) {
    this.endpoint = endpoint;
    this.socket = null;
    this.listeners = new Set();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.connected = false;
  }

  connect() {
    if (this.socket) return;
    
    // Construct ws URL from http endpoint
    const url = new URL(this.endpoint, window.location.href);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    
    this.socket = new WebSocket(url.toString());

    this.socket.onopen = () => {
      this.connected = true;
      this.reconnectAttempts = 0;
      console.log(`[WebSocket] Connected to ${url.toString()}`);
    };

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.listeners.forEach(fn => fn(data));
      } catch (err) {
        console.error('[WebSocket] Failed to parse message', err);
      }
    };

    this.socket.onclose = () => {
      this.connected = false;
      this.socket = null;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        setTimeout(() => this.connect(), 1000 * Math.pow(2, this.reconnectAttempts));
      } else {
        console.error('[WebSocket] Max reconnect attempts reached');
      }
    };

    this.socket.onerror = (err) => {
      console.error('[WebSocket] Error', err);
    };
  }

  subscribe(fn) {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}

export const globalWsAdapter = new WebSocketAdapter('/api/v1/stream/ws');
