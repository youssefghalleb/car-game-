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
    this._playerId = null;
    this._role = 'display';
    this._reconnectAttempts = 0;
    this._maxReconnectAttempts = 5;
    this._reconnecting = false;
    this._trackCache = null;
    this._connectSeq = 0;
    this._manualClose = false;
    this._reconnectTimer = null;
    this._configPromise = null;
  }

  on(event, callback) {
    if (!this._listeners[event]) this._listeners[event] = [];
    this._listeners[event].push(callback);
  }

  _emit(event, data) {
    (this._listeners[event] || []).forEach(cb => cb(data));
  }

  _normalizeRoomId(roomId) {
    return String(roomId || '')
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, '')
      .slice(0, 32);
  }

  _getWsBaseUrl() {
    if (!this._configPromise) {
      this._configPromise = fetch('/api/config')
        .then((response) => (response.ok ? response.json() : {}))
        .then((config) => String(config.gameServerWsUrl || '').replace(/\/$/, ''))
        .catch(() => '');
    }
    return this._configPromise;
  }

  connect(roomId) {
    roomId = this._normalizeRoomId(roomId);
    if (!roomId) return;
    if (
      this.ws &&
      this._roomId === roomId &&
      (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    this._roomId = roomId;
    this._manualClose = false;
    this._connectSeq += 1;
    const seq = this._connectSeq;

    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws && this.ws.readyState !== WebSocket.CLOSED) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close(1000, 'replaced');
    }

    this._getWsBaseUrl().then((configuredWsBase) => {
      if (seq !== this._connectSeq) return;
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsBase = configuredWsBase || `${protocol}//${window.location.host}`;
      const url = `${wsBase}/ws/${encodeURIComponent(roomId)}`;
      console.info(`[WS] connecting room=${roomId} url=${url}`);
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
      if (seq !== this._connectSeq) return;
      this.connected = true;
      this._reconnectAttempts = 0;
      console.info(`[WS] connected room=${roomId}`);
      this._emit('connected');
      // Re-join room after reconnect
      if (this._reconnecting && this._playerName) {
        this.join(this._playerName, { role: this._role, playerId: this._playerId });
        this._reconnecting = false;
      }
      };

      this.ws.onmessage = (event) => {
      if (seq !== this._connectSeq) return;
      try {
        const data = JSON.parse(event.data);
        if (data.action === 'joined') {
          this._playerId = data.player_id || this._playerId;
          this._role = data.role || this._role;
          this._emit('joined', data);
        } else if (data.error) {
          this._emit('error', {
            code: data.error,
            message: data.blockers?.length ? data.blockers.join(' · ') : data.error,
          });
        } else {
          if (data.track) {
            this._trackCache = data.track;
          } else if (this._trackCache && data.cars) {
            data.track = this._trackCache;
          }
          this._emit('state', data);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
      };

      this.ws.onclose = (event) => {
      if (seq !== this._connectSeq) return;
      this.connected = false;
      console.info(`[WS] closed room=${roomId} code=${event.code} reason=${event.reason || ''}`);
      const replaced = event.code === 4001 || event.reason === 'replaced';
      if (!this._manualClose && !replaced && this._reconnectAttempts < this._maxReconnectAttempts) {
        this._attemptReconnect();
      } else {
        this._emit('disconnected');
      }
      };

      this.ws.onerror = (event) => {
      if (seq !== this._connectSeq) return;
      console.warn('[WS] socket error', event);
      this._emit('error', 'Connection failed');
      };
    });
  }

  _attemptReconnect() {
    this._reconnectAttempts++;
    this._reconnecting = true;
    const delay = Math.min(1000 * Math.pow(2, this._reconnectAttempts - 1), 10000);
    console.log(`[WS] Reconnecting in ${delay}ms (attempt ${this._reconnectAttempts}/${this._maxReconnectAttempts})`);
    this._reconnectTimer = setTimeout(() => {
      this._reconnectTimer = null;
      if (!this.connected) {
        this.connect(this._roomId);
      }
    }, delay);
  }

  disconnect() {
    this._manualClose = true;
    this._connectSeq += 1;
    if (this._reconnectTimer) {
      clearTimeout(this._reconnectTimer);
      this._reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
      this.connected = false;
    }
  }

  send(data) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  join(name, options = {}) {
    this._playerName = name;
    this._playerId = options.playerId || null;
    this._role = options.role || 'display';
    this.send({
      action: 'join',
      role: this._role,
      name,
      player_id: this._playerId,
    });
  }

  spectate(name) {
    this.join(name, { role: 'spectator' });
  }

  sendInput(controls) {
    this.send({ action: 'input', ...controls });
  }

  startRace() {
    this.send({ action: 'start' });
  }

  setReady(ready) {
    this.send({ action: 'ready', ready: !!ready });
  }

  updateSettings(settings) {
    this.send({ action: 'settings', ...settings });
  }

  sendChat(text) {
    this.send({ action: 'chat', text });
  }

  pauseRace() {
    this.send({ action: 'pause' });
  }

  resumeRace() {
    this.send({ action: 'resume' });
  }

  restartRace() {
    this.send({ action: 'restart' });
  }

  resetRace() {
    this.send({ action: 'reset' });
  }

  quitRace() {
    this.send({ action: 'quit' });
  }
}
