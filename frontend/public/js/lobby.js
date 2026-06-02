// ============================================================
// Lobby UI logic
// ============================================================

export class LobbyUI {
  constructor(client) {
    this.client = client;
    this._joined = false;

    this.joinBtn = document.getElementById('join-btn');
    this.readyBtn = document.getElementById('ready-btn');
    this.startBtn = document.getElementById('start-btn');
    this.statusEl = document.getElementById('lobby-status');
    this.playerListEl = document.getElementById('player-list-ul');
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
    this._pendingJoinName = null;
    this._ready = false;
    this._myPlayerId = null;

    this.joinBtn.addEventListener('click', () => this._onJoin());
    this.readyBtn.addEventListener('click', () => this._onReadyToggle());
    this.startBtn.addEventListener('click', () => this._onStart());
    this.client.on('connected', () => {
      if (this._pendingJoinName) {
        this.client.join(this._pendingJoinName);
        this._pendingJoinName = null;
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
    this.client.connect(roomCode);
  }

  _onStart() {
    if (!this.client.connected) {
      this.showStatus('Error: not connected to server');
      return;
    }

    // Send settings then start
    const settings = {
      race_mode: document.getElementById('mode-select').value,
      track_layout: document.getElementById('track-select').value,
      laps_to_win: parseInt(document.getElementById('laps-select').value),
      bot_count: parseInt(document.getElementById('bots-select').value),
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
    this.showStatus(`Joined room: ${data.room_id} (You are Player ${data.player_id})`);
    this.joinBtn.classList.add('hidden');
    this.readyBtn.classList.remove('hidden');
    this.startBtn.classList.remove('hidden');
    this.startBtn.disabled = true;
    this.showPairing(data.room_id, data.player_id);
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
    this.overviewSpectatorsEl.textContent = '0';
    this.playerListEl.innerHTML = Object.entries(players)
      .map(([id, p]) => {
        const controller = p.controller ? (p.controller_ready ? 'Controller ready' : 'Controller linked') : 'Scan QR';
        const monitor = p.ready ? 'Ready' : 'Waiting';
        const ping = p.ping_ms ? `${p.ping_ms}ms` : '-';
        return `
          <li>
            <span>${id} · ${this._escape(p.name)} · Roadster</span>
            <span>${monitor} · ${controller} · ${ping}</span>
          </li>
        `;
      })
      .join('');
  }

  updateStartState(state) {
    if (!this._joined) return;
    const canStart = !!state.can_start;
    this.startBtn.disabled = !canStart;
    this.startBtn.classList.toggle('disabled', !canStart);
    if (state.players?.[this._myPlayerId]) {
      this._ready = !!state.players[this._myPlayerId].ready;
      this._updateReadyButton();
    }
    this.overviewModeEl.textContent = this._formatMode(state.settings?.race_mode || state.race_mode || 'sprint');
    this.overviewTrackEl.textContent = this._formatTrack(state.settings?.track_layout || 'track_1');
    if (canStart) {
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
}
