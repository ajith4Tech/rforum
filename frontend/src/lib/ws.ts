import { WS_ORIGIN } from './api';

export type MessageHandler = (data: any) => void;
export type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting';
export type StatusHandler = (status: ConnectionStatus) => void;

// Upper bound for the reconnect backoff (see scheduleReconnect) — caps how
// long a client waits before retrying and, combined with full jitter, how
// spread-out a mass-reconnect wave is after a shared disruption.
const MAX_RECONNECT_DELAY_MS = 15000;

export interface WsConnectOptions {
  /** JWT of the authenticated session owner — identifies this connection as a moderator. */
  token?: string;
  /** Marks this connection as a read-only projector/screen client. */
  role?: 'screen';
}

export class RforumWebSocket {
  private code: string;
  private opts: WsConnectOptions;
  private socket: WebSocket | null = null;
  private reconnectBackoff = 500;
  private handler: MessageHandler | null = null;
  private statusHandler: StatusHandler | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  public status: ConnectionStatus = 'disconnected';

  constructor(code: string, opts: WsConnectOptions = {}) {
    this.code = code;
    this.opts = opts;
  }

  onStatusChange(handler: StatusHandler) {
    this.statusHandler = handler;
  }

  private setStatus(status: ConnectionStatus) {
    this.status = status;
    this.statusHandler?.(status);
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
    this.setStatus('disconnected');
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
      this.setStatus('connected');
      this.startHeartbeat();
    };

    this.socket.onclose = () => {
      this.stopHeartbeat();
      if (!this.closed) {
        this.setStatus('reconnecting');
        this.scheduleReconnect();
      } else {
        this.setStatus('disconnected');
      }
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
    // Full jitter (0..cap) rather than a fixed delay: after a shared
    // disruption (backend restart, network blip) hundreds of clients would
    // otherwise retry in lockstep, creating a reconnect storm that hammers
    // the same per-IP WS connect rate limit on every synchronized wave.
    const cap = Math.min(this.reconnectBackoff, MAX_RECONNECT_DELAY_MS);
    const delay = Math.random() * cap;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.reconnectBackoff = Math.min(this.reconnectBackoff * 2, MAX_RECONNECT_DELAY_MS);
      this.openSocket();
    }, delay);
  }

  private buildUrl() {
    const base = (WS_ORIGIN || '').replace(/\/$/, '');
    const path = `/ws/${this.code}${this.buildQuery()}`;
    if (base) return `${base}${path}`;

    // Fallback to API origin converted to WS if available
    // Otherwise use current origin
    const api = (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000');
    const wsBase = api.replace(/^http/, 'ws');
    return `${wsBase}${path}`;
  }

  private buildQuery() {
    const params = new URLSearchParams();
    if (this.opts.token) params.set('token', this.opts.token);
    if (this.opts.role) params.set('role', this.opts.role);
    const qs = params.toString();
    return qs ? `?${qs}` : '';
  }
}
