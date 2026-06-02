// ============================================================
// Lobby UI logic
// ============================================================

export class LobbyUI {
  constructor(client) {
    this.client = client;
    this._joined = false;

    this.joinBtn = document.getElementById('join-btn');
    this.spectateBtn = document.getElementById('spectate-btn');
    this.readyBtn = document.getElementById('ready-btn');
    this.startBtn = document.getElementById('start-btn');
    this.statusEl = document.getElementById('lobby-status');
    this.playerListEl = document.getElementById('player-list-ul');
    this.chatLogEl = document.getElementById('chat-log');
    this.chatInputEl = document.getElementById('chat-input');
    this.chatSendBtn = document.getElementById('chat-send-btn');
    this.recordsSummaryEl = document.getElementById('records-summary');
    this.pairingCard = document.getElementById('pairing-card');
    this.pairRoomEl = document.getElementById('pair-room');
    this.pairPlayerEl = document.getElementById('pair-player');
    this.controllerLinkEl = document.getElementById('controller-link');
    this.qrEl = document.getElementById('pair-qr');
    this.overviewRoomEl = document.getElementById('overview-room');
    this.overviewPlayersEl = document.getElementById('overview-players');
    this.overviewSpectatorsEl = document.getElementById('overview-spectators');
    this.overviewModeEl = document.getElementById('overview-mode');
    this.overviewTrackEl = document.getElementById('overview-track');
    this.modeSelect = document.getElementById('mode-select');
    this.lapsSelect = document.getElementById('laps-select');
    this.botsSelect = document.getElementById('bots-select');
    this._pendingJoinName = null;
    this._pendingJoinRole = 'display';
    this._ready = false;
    this._myPlayerId = null;
    this._isSpectator = false;
    this._isHost = false;
    this._lastChatKey = '';

    this.joinBtn.addEventListener('click', () => this._onJoin());
    this.spectateBtn.addEventListener('click', () => this._onSpectate());
    this.readyBtn.addEventListener('click', () => this._onReadyToggle());
    this.startBtn.addEventListener('click', () => this._onStart());
    this.chatSendBtn.addEventListener('click', () => this._sendChat());
    this.chatInputEl.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') this._sendChat();
    });
    this.modeSelect.addEventListener('change', () => this._syncModeControls());
    this._syncModeControls();
    this.updateRecords();
    this.client.on('connected', () => {
      if (this._pendingJoinName) {
        if (this._pendingJoinRole === 'spectator') {
          this.client.spectate(this._pendingJoinName);
        } else {
          this.client.join(this._pendingJoinName);
        }
        this._pendingJoinName = null;
        this._pendingJoinRole = 'display';
      }
    });
  }

  _onReadyToggle() {
    this._ready = !this._ready;
    this.client.setReady(this._ready);
    this._updateReadyButton();
  }

  _onJoin() {
    const name = document.getElementById('player-name').value.trim() || 'Player';
    const roomCode = this._normalizeRoomCode(
      document.getElementById('room-code').value.trim() || this._generateCode()
    );

    document.getElementById('room-code').value = roomCode;

    this.showStatus('Connecting...');
    this._pendingJoinName = name;
    this._pendingJoinRole = 'display';
    this.client.connect(roomCode);
  }

  _onSpectate() {
    const name = document.getElementById('player-name').value.trim() || 'Spectator';
    const roomCode = this._normalizeRoomCode(document.getElementById('room-code').value.trim());
    if (!roomCode) {
      this.showStatus('Enter a room code to spectate');
      return;
    }

    document.getElementById('room-code').value = roomCode;
    this.showStatus('Connecting as spectator...');
    this._pendingJoinName = name;
    this._pendingJoinRole = 'spectator';
    this.client.connect(roomCode);
  }

  _onStart() {
    if (!this.client.connected) {
      this.showStatus('Error: not connected to server');
      return;
    }

    // Send settings then start
    const raceMode = this.modeSelect.value;
    const settings = {
      race_mode: raceMode,
      track_layout: document.getElementById('track-select').value,
      laps_to_win: raceMode === 'elimination' ? 0 : parseInt(this.lapsSelect.value),
      bot_count: this._modeUsesBots(raceMode) ? parseInt(this.botsSelect.value) : 0,
      bot_difficulty: document.getElementById('difficulty-select').value,
      car_damage: document.getElementById('damage-select').value === 'true',
      steer_assist: document.getElementById('assist-select').value,
    };
    this.client.updateSettings(settings);

    setTimeout(() => {
      this.client.startRace();
    }, 100);
  }

  _generateCode() {
    return Math.random().toString(36).substring(2, 8).toUpperCase();
  }

  _normalizeRoomCode(value) {
    return String(value || '')
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, '')
      .slice(0, 32);
  }

  onJoined(data) {
    this._joined = true;
    this._myPlayerId = data.player_id;
    this._isSpectator = data.role === 'spectator';
    this.showStatus(this._isSpectator
      ? `Spectating room: ${data.room_id}`
      : `Joined room: ${data.room_id} (You are Player ${data.player_id})`
    );
    this.joinBtn.classList.add('hidden');
    this.spectateBtn.classList.add('hidden');
    this.readyBtn.classList.toggle('hidden', this._isSpectator);
    this.startBtn.classList.toggle('hidden', this._isSpectator);
    this.startBtn.disabled = true;
    if (!this._isSpectator) {
      this.showPairing(data.room_id, data.player_id);
    }
    this.overviewRoomEl.textContent = data.room_id;
    this._updateReadyButton();
  }

  showPairing(roomId, playerId) {
    const controllerUrl = new URL('/controller.html', window.location.origin);
    controllerUrl.searchParams.set('room', roomId);
    controllerUrl.searchParams.set('player', playerId);

    this.pairRoomEl.textContent = roomId;
    this.pairPlayerEl.textContent = playerId;
    this.controllerLinkEl.href = controllerUrl.toString();
    this.controllerLinkEl.textContent = controllerUrl.pathname + controllerUrl.search;
    console.info(`[Pairing] controller room=${roomId} player=${playerId} url=${controllerUrl.toString()}`);
    this.qrEl.src = `https://api.qrserver.com/v1/create-qr-code/?size=180x180&data=${encodeURIComponent(controllerUrl.toString())}`;
    this.pairingCard.classList.remove('hidden');
  }

  updatePlayers(players) {
    if (!players) return;
    this.overviewPlayersEl.textContent = Object.keys(players).length;
    this.playerListEl.innerHTML = Object.entries(players)
      .map(([id, p]) => {
        const controller = p.controller ? (p.controller_ready ? 'Controller ready' : 'Controller linked') : 'Scan QR';
        const monitor = p.ready ? 'Ready' : 'Waiting';
        const ping = p.ping_ms ? `${p.ping_ms}ms` : '-';
        const host = p.host ? 'Host' : 'Player';
        return `
          <li>
            <span>${id} · ${this._escape(p.name)} · ${host} · Roadster</span>
            <span>${monitor} · ${controller} · ${ping}</span>
          </li>
        `;
      })
      .join('');
  }

  updateStartState(state) {
    if (!this._joined) return;
    this._isHost = !!state.players?.[this._myPlayerId]?.host;
    this.overviewSpectatorsEl.textContent = Object.keys(state.spectators || {}).length;
    this._updateChat(state.chat || []);
    this._syncHostControls();
    if (this._isSpectator) {
      this.showStatus(state.state === 'lobby' ? 'Spectating lobby' : 'Spectating race');
      return;
    }
    const canStart = !!state.can_start;
    this.startBtn.disabled = !canStart || !this._isHost;
    this.startBtn.classList.toggle('disabled', !canStart || !this._isHost);
    if (state.players?.[this._myPlayerId]) {
      this._ready = !!state.players[this._myPlayerId].ready;
      this._updateReadyButton();
    }
    this.overviewModeEl.textContent = this._formatMode(state.settings?.race_mode || state.race_mode || 'sprint');
    this.overviewTrackEl.textContent = this._formatTrack(state.settings?.track_layout || 'track_1');
    if (!this._isHost) {
      this.showStatus('Waiting for host');
    } else if (canStart) {
      this.showStatus('All players ready');
    } else if (state.start_blockers?.length) {
      this.showStatus(state.start_blockers.slice(0, 2).join(' · '));
    }
  }

  showStatus(msg) {
    this.statusEl.textContent = msg;
  }

  _updateReadyButton() {
    this.readyBtn.textContent = this._ready ? 'Ready ✓' : 'Ready';
    this.readyBtn.classList.toggle('success', this._ready);
  }

  _escape(value) {
    return String(value).replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  _formatMode(mode) {
    return {
      sprint: 'Sprint',
      time_trial: 'Time Trial',
      practice: 'Practice',
      elimination: 'Elimination',
    }[mode] || 'Sprint';
  }

  _formatTrack(track) {
    return track === 'track_2' ? 'Circuit 2' : 'Circuit 1';
  }

  updateRecords() {
    if (!this.recordsSummaryEl) return;
    let records = {};
    try {
      records = JSON.parse(localStorage.getItem('carGameRecords') || '{}');
    } catch (_) {
      records = {};
    }

    const achievements = records.achievements || [];
    this.recordsSummaryEl.innerHTML = `
      <span>Best Lap<strong>${this._formatTime(records.best_lap)}</strong></span>
      <span>Best Race<strong>${this._formatTime(records.best_race_time)}</strong></span>
      <span>Races<strong>${records.races_completed || 0}</strong></span>
      <span>Wins<strong>${records.wins || 0}</strong></span>
      <span>Podiums<strong>${records.podiums || 0}</strong></span>
      <span>Achievements<strong>${achievements.length}</strong></span>
    `;
  }

  _modeUsesBots(mode) {
    return mode === 'sprint' || mode === 'elimination';
  }

  _syncModeControls() {
    const mode = this.modeSelect.value;
    const botsDisabled = !this._modeUsesBots(mode);
    const lapsDisabled = mode === 'practice' || mode === 'elimination';

    this.botsSelect.disabled = botsDisabled;
    this.lapsSelect.disabled = lapsDisabled;
    if (botsDisabled) this.botsSelect.value = '0';
    this._syncHostControls();
  }

  _syncHostControls() {
    const enabled = !this._joined || this._isHost;
    [
      this.modeSelect,
      document.getElementById('track-select'),
      this.lapsSelect,
      this.botsSelect,
      document.getElementById('difficulty-select'),
      document.getElementById('damage-select'),
      document.getElementById('assist-select'),
    ].forEach((el) => {
      if (!el) return;
      el.disabled = !enabled || el.disabled && (el === this.lapsSelect || el === this.botsSelect);
    });

    const mode = this.modeSelect.value;
    if (enabled) {
      this.botsSelect.disabled = !this._modeUsesBots(mode);
      this.lapsSelect.disabled = mode === 'practice' || mode === 'elimination';
    }
  }

  _sendChat() {
    const text = this.chatInputEl.value.trim();
    if (!text || !this.client.connected) return;
    this.client.sendChat(text);
    this.chatInputEl.value = '';
  }

  _updateChat(messages) {
    const key = messages.map(m => `${m.time}:${m.sender}:${m.text}`).join('|');
    if (key === this._lastChatKey) return;
    this._lastChatKey = key;
    this.chatLogEl.innerHTML = messages.slice(-20).map((m) => `
      <div class="chat-message"><strong>${this._escape(m.sender)}</strong> ${this._escape(m.text)}</div>
    `).join('');
    this.chatLogEl.scrollTop = this.chatLogEl.scrollHeight;
  }

  _formatTime(value) {
    return Number.isFinite(value) ? `${value.toFixed(2)}s` : '-';
  }
}
