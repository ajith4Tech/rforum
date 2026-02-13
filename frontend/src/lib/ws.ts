type MessageHandler = (message: any) => void;

export class RforumWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Set<MessageHandler> = new Set();
  private sessionCode: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  private readonly apiOrigin = (import.meta as any)?.env?.VITE_API_ORIGIN as string | undefined;

  constructor(sessionCode: string) {
    this.sessionCode = sessionCode;
  }

  connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;

    const wsOrigin = this.apiOrigin
      ? this.apiOrigin.replace(/^http/i, 'ws')
      : `${protocol}//${host}`;

    this.ws = new WebSocket(`${wsOrigin}/ws/${this.sessionCode}`);

    this.ws.onopen = () => {
      console.log(`[WS] Connected to session ${this.sessionCode}`);
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.handlers.forEach((handler) => handler(message));
      } catch (e) {
        console.error('[WS] Failed to parse message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('[WS] Connection closed');
      this.attemptReconnect();
    };

    this.ws.onerror = (error) => {
      console.error('[WS] Error:', error);
    };
  }

  private attemptReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('[WS] Max reconnect attempts reached');
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectAttempts++;

    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  send(event: string, data: object = {}) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ event, data }));
    }
  }

  onMessage(handler: MessageHandler) {
    this.handlers.add(handler);
    return () => this.handlers.delete(handler);
  }

  disconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectAttempts = this.maxReconnectAttempts; // prevent reconnect
    this.ws?.close();
    this.ws = null;
    this.handlers.clear();
  }
}
