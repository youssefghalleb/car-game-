// ============================================================
// WebSocket client for game server communication
// ============================================================

export class GameClient {
  constructor() {
    this.ws = null;
    this.connected = false;
    this._listeners = {};
  }

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach(cb => cb(data));
  }

  connect(roomId) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${roomId}`;
    console.log('[WS] Connecting to:', url);

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.connected = true;
      this._emit('connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[WS] Received:', data.action || data.state || 'state-update', data);
        if (data.action === 'joined') {
          this._emit('joined', data);
        } else if (data.error) {
          this._emit('error', data.error);
        } else {
          this._emit('state', data);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    this.ws.onclose = (event) => {
      console.log('[WS] Disconnected, code:', event.code, 'reason:', event.reason);
      this.connected = false;
      this._emit('disconnected');
    };

    this.ws.onerror = (event) => {
      console.error('[WS] Error:', event);
      this._emit('error', 'Connection failed');
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('[WS] Sending:', data);
      this.ws.send(JSON.stringify(data));
    } else {
      console.warn('[WS] Cannot send, readyState:', this.ws?.readyState, 'data:', data);
    }
  }

  join(name) {
    this.send({ action: 'join', name });
  }

  sendInput(controls) {
    this.send({ action: 'input', ...controls });
  }

  startRace() {
    this.send({ action: 'start' });
  }

  updateSettings(settings) {
    this.send({ action: 'settings', ...settings });
  }
}
