// ============================================================
// Lobby UI logic
// ============================================================

export class LobbyUI {
  constructor(client) {
    this.client = client;
    this._joined = false;

    this.joinBtn = document.getElementById('join-btn');
    this.startBtn = document.getElementById('start-btn');
    this.statusEl = document.getElementById('lobby-status');
    this.playerListEl = document.getElementById('player-list-ul');

    this.joinBtn.addEventListener('click', () => this._onJoin());
    this.startBtn.addEventListener('click', () => this._onStart());
  }

  _onJoin() {
    const name = document.getElementById('player-name').value.trim() || 'Player';
    const roomCode = document.getElementById('room-code').value.trim() || this._generateCode();

    document.getElementById('room-code').value = roomCode;

    this.showStatus('Connecting...');
    this.client.connect(roomCode);
    this.client.on('connected', () => {
      this.client.join(name);
    });
  }

  _onStart() {
    console.log('[Lobby] Start button clicked');
    console.log('[Lobby] Client connected:', this.client.connected);
    console.log('[Lobby] WS state:', this.client.ws?.readyState);

    if (!this.client.connected) {
      this.showStatus('Error: not connected to server');
      return;
    }

    // Send settings then start
    const settings = {
      track_layout: document.getElementById('track-select').value,
      laps_to_win: parseInt(document.getElementById('laps-select').value),
      bot_count: parseInt(document.getElementById('bots-select').value),
      bot_difficulty: document.getElementById('difficulty-select').value,
    };
    console.log('[Lobby] Sending settings:', settings);
    this.client.updateSettings(settings);

    setTimeout(() => {
      console.log('[Lobby] Sending start command');
      this.client.startRace();
    }, 100);
  }

  _generateCode() {
    return Math.random().toString(36).substring(2, 8).toUpperCase();
  }

  onJoined(data) {
    this._joined = true;
    this.showStatus(`Joined room: ${data.room_id} (You are Player ${data.player_id})`);
    this.joinBtn.classList.add('hidden');
    this.startBtn.classList.remove('hidden');
  }

  updatePlayers(players) {
    if (!players) return;
    this.playerListEl.innerHTML = Object.entries(players)
      .map(([id, p]) => `<li>🏎️ ${p.name} ${p.ready ? '✓' : ''}</li>`)
      .join('');
  }

  showStatus(msg) {
    this.statusEl.textContent = msg;
  }
}
