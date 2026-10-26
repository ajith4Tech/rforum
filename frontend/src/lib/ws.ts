import { WS_ORIGIN } from './api';

export type MessageHandler = (data: any) => void;
/** 'offline' = the browser reports no network at all; 'reconnecting' = the
 * network is up (or unknown) but the socket is down and retrying. */
export type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting' | 'offline';
export type StatusHandler = (status: ConnectionStatus) => void;

// Upper bound for the reconnect backoff (see scheduleReconnect) — caps how
// long a client waits before retrying and, combined with full jitter, how
// spread-out a mass-reconnect wave is after a shared disruption.
const MAX_RECONNECT_DELAY_MS = 15000;
const MAX_PENDING_MESSAGES = 50;
// A buffered control older than this is dropped instead of being delivered on
// reconnect — after a long outage, "refresh the screen" or "show the QR" is no
// longer what the presenter means, and receivers resync authoritative state on
// reconnect anyway.
const PENDING_MESSAGE_TTL_MS = 15000;
const HEARTBEAT_INTERVAL_MS = 15000;
// With the server answering every ping (15s), this much silence means the
// connection is half-open (common on flaky Wi-Fi): it still reports OPEN but
// delivers nothing, so close it and let the normal reconnect path take over.
const LIVENESS_TIMEOUT_MS = 45000;
// Transient commands that are only meaningful at the moment they are sent —
// never buffered: replaying an old play/seek after reconnect would yank the
// projector to a stale position.
const UNBUFFERED_EVENTS = new Set(['video_control']);

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
  // A presenter can click a control while this socket is still opening (or
  // reconnecting). Keep those messages so controls such as refresh/QR do not
  // disappear without reaching the projector.
  private pendingMessages: { message: string; queuedAt: number }[] = [];
  public status: ConnectionStatus = 'disconnected';
  private listeningForNetwork = false;
  private lastMessageAt = 0;
  // Only enforce the liveness timeout once this socket's server has proven it
  // answers pings — an older backend that never replies must not be torn down.
  private serverAnswersPing = false;

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
    this.listenForNetworkChanges();
    this.openSocket();
  }

  private isBrowserOffline() {
    return typeof navigator !== 'undefined' && navigator.onLine === false;
  }

  private handleOnline = () => {
    if (this.closed || this.socket?.readyState === WebSocket.OPEN) return;
    // Network is back: retry now instead of waiting out the current backoff
    // (up to MAX_RECONNECT_DELAY_MS).
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectBackoff = 500;
    this.setStatus('reconnecting');
    // A CONNECTING/CLOSING socket finishes its own cycle (onopen, or onclose →
    // scheduleReconnect at the reset backoff); opening another now would leave
    // two live sockets delivering every message twice.
    if (this.socket && this.socket.readyState !== WebSocket.CLOSED) return;
    this.openSocket();
  };

  private handleOffline = () => {
    if (this.closed) return;
    // The socket typically still reports OPEN until TCP gives up (minutes),
    // but nothing can arrive — don't keep claiming "connected".
    if (this.socket) this.abandonSocket();
    else this.setStatus('offline');
  };

  /** Drop the current socket without waiting for its close handshake (which a
   * dead link can't complete) and start the normal reconnect cycle. Its
   * handlers ignore it from here on (see openSocket). */
  private abandonSocket() {
    const sock = this.socket;
    this.socket = null;
    this.stopHeartbeat();
    try { sock?.close(); } catch { /* already closing */ }
    this.setStatus(this.isBrowserOffline() ? 'offline' : 'reconnecting');
    this.scheduleReconnect();
  }

  private listenForNetworkChanges() {
    if (this.listeningForNetwork || typeof window === 'undefined') return;
    window.addEventListener('online', this.handleOnline);
    window.addEventListener('offline', this.handleOffline);
    this.listeningForNetwork = true;
  }

  private stopListeningForNetworkChanges() {
    if (!this.listeningForNetwork || typeof window === 'undefined') return;
    window.removeEventListener('online', this.handleOnline);
    window.removeEventListener('offline', this.handleOffline);
    this.listeningForNetwork = false;
  }

  onMessage(handler: MessageHandler) {
    this.handler = handler;
  }

  /** Returns true when the message was sent or buffered for delivery on
   * reconnect, false when it was dropped. A buffered message has NOT reached
   * anyone yet — callers must not present it as delivered. */
  send(event: string, data: any): boolean {
    const message = JSON.stringify({ event, data });
    if (this.socket?.readyState === WebSocket.OPEN) {
      try {
        this.socket.send(message);
        return true;
      } catch (error) {
        console.warn('[ws] send failed; queuing for reconnect', error);
      }
    }

    if (this.closed || UNBUFFERED_EVENTS.has(event) || this.pendingMessages.length >= MAX_PENDING_MESSAGES) return false;
    this.pendingMessages.push({ message, queuedAt: Date.now() });
    return true;
  }

  disconnect() {
    this.closed = true;
    this.pendingMessages = [];
    this.stopListeningForNetworkChanges();
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
    const sock = new WebSocket(url);
    this.socket = sock;

    // Every handler ignores events from a socket that is no longer current,
    // so a superseded socket can never deliver duplicates or spawn a second
    // reconnect loop.
    sock.onmessage = (event) => {
      if (this.socket !== sock) return;
      this.lastMessageAt = Date.now();
      try {
        const data = JSON.parse(event.data);
        if (data?.event === 'pong') {
          this.serverAnswersPing = true;
          return;
        }
        this.handler?.(data);
      } catch (err) {
        console.warn('[ws] failed to parse message', err);
      }
    };

    sock.onopen = () => {
      if (this.socket !== sock) return;
      this.reconnectBackoff = 500;
      this.lastMessageAt = Date.now();
      this.serverAnswersPing = false;
      this.setStatus('connected');
      this.startHeartbeat();
      this.flushPendingMessages();
    };

    sock.onclose = () => {
      if (this.socket !== sock) return;
      this.stopHeartbeat();
      if (!this.closed) {
        this.setStatus(this.isBrowserOffline() ? 'offline' : 'reconnecting');
        this.scheduleReconnect();
      } else {
        this.setStatus('disconnected');
      }
    };

    sock.onerror = () => {
      if (this.socket !== sock) return;
      this.stopHeartbeat();
      sock.close();
    };
  }

  private startHeartbeat() {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      const sock = this.socket;
      if (sock?.readyState !== WebSocket.OPEN) return;
      if (this.serverAnswersPing && Date.now() - this.lastMessageAt > LIVENESS_TIMEOUT_MS) {
        console.warn('[ws] no traffic from server; reconnecting');
        this.abandonSocket();
        return;
      }
      sock.send(JSON.stringify({ event: 'ping', data: Date.now() }));
    }, HEARTBEAT_INTERVAL_MS);
  }

  private flushPendingMessages() {
    const cutoff = Date.now() - PENDING_MESSAGE_TTL_MS;
    this.pendingMessages = this.pendingMessages.filter((entry) => entry.queuedAt >= cutoff);
    while (this.pendingMessages.length && this.socket?.readyState === WebSocket.OPEN) {
      const { message } = this.pendingMessages[0];
      try {
        this.socket.send(message);
        this.pendingMessages.shift();
      } catch (error) {
        console.warn('[ws] failed to flush pending message', error);
        break;
      }
    }
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
