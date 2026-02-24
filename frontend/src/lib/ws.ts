import { WS_ORIGIN } from './api';

export type MessageHandler = (data: any) => void;

export class RforumWebSocket {
  private code: string;
  private socket: WebSocket | null = null;
  private reconnectBackoff = 500;
  private handler: MessageHandler | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;

  constructor(code: string) {
    this.code = code;
  }

  connect(handler?: MessageHandler) {
    if (handler) this.handler = handler;
    this.closed = false;
    this.openSocket();
  }

  onMessage(handler: MessageHandler) {
    this.handler = handler;
  }

  send(event: string, data: any) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ event, data }));
    }
  }

  disconnect() {
    this.closed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  private openSocket() {
    const url = this.buildUrl();
    this.socket = new WebSocket(url);

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handler?.(data);
      } catch (err) {
        console.warn('[ws] failed to parse message', err);
      }
    };

    this.socket.onopen = () => {
      this.reconnectBackoff = 500;
      this.startHeartbeat();
    };

    this.socket.onclose = () => {
      this.stopHeartbeat();
      if (!this.closed) this.scheduleReconnect();
    };

    this.socket.onerror = () => {
      this.stopHeartbeat();
      this.socket?.close();
    };
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      if (this.socket?.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({ event: 'ping', data: Date.now() }));
      }
    }, 15000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer || this.closed) return;
    const delay = Math.min(this.reconnectBackoff, 8000);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectBackoff = Math.min(this.reconnectBackoff * 2, 8000);
      this.openSocket();
    }, delay);
  }

  private buildUrl() {
    const base = (WS_ORIGIN || '').replace(/\/$/, '');
    if (base) return `${base}/ws/${this.code}`;

    // Fallback to API origin converted to WS if available
    // Otherwise use current origin
    const api = (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
    const wsBase = api.replace(/^http/, 'ws');
    return `${wsBase}/ws/${this.code}`;
  }
}
