// ============================================================
// WebSocket client for game server communication
// ============================================================

export class GameClient {
  constructor() {
    this.ws = null;
    this.connected = false;
    this._listeners = {};
    this._roomId = null;
    this._playerName = null;
    this._reconnectAttempts = 0;
    this._maxReconnectAttempts = 5;
    this._reconnecting = false;
  }

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach(cb => cb(data));
  }

  connect(roomId) {
    this._roomId = roomId;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/${roomId}`;
    console.log('[WS] Connecting to:', url);

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('[WS] Connected');
      this.connected = true;
      this._reconnectAttempts = 0;
      this._emit('connected');
      // Re-join room after reconnect
      if (this._reconnecting && this._playerName) {
        this.join(this._playerName);
        this._reconnecting = false;
      }
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
      // Error 1006 = abnormal closure — attempt reconnect
      if (event.code === 1006 && this._reconnectAttempts < this._maxReconnectAttempts) {
        this._attemptReconnect();
      } else {
        this._emit('disconnected');
      }
    };

    this.ws.onerror = (event) => {
      console.error('[WS] Error:', event);
    };
  }

  _attemptReconnect() {
    this._reconnectAttempts++;
    this._reconnecting = true;
    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts - 1), 10000);
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this._reconnectAttempts}/${this._maxReconnectAttempts})`);
    setTimeout(() => {
      if (!this.connected) {
        this.connect(this._roomId);
      }
    }, delay);
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
    this._playerName = name;
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
