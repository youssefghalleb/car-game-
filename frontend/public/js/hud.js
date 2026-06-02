// ============================================================
// HUD - heads up display during race
// ============================================================

export class HUD {
  constructor() {
    this.posEl = document.getElementById('hud-position');
    this.lapEl = document.getElementById('hud-lap');
    this.speedEl = document.getElementById('hud-speed');
    this.timeEl = document.getElementById('hud-time');
    this.nitroFill = document.getElementById('hud-nitro-fill');
    this.healthFill = document.getElementById('hud-health-fill');
    this.warningEl = document.getElementById('race-warning');
    this.leaderboardEl = document.getElementById('leaderboard-list');
    this.minimapCanvas = document.getElementById('minimap-canvas');
    this.minimapCtx = this.minimapCanvas?.getContext('2d');
    this._minimapTrackKey = null;
    this._minimapTrackCanvas = null;
  }

  update(state, myPlayerId) {
    if (!state.cars) return;

    const myCar = state.cars.find(c => c.id === myPlayerId);
    if (!myCar) return;

    // Position in race
    const raceMode = state.race_mode || 'sprint';
    const sorted = this._sortCars(state.cars, raceMode);
    const position = sorted.findIndex(c => c.id === myPlayerId) + 1;
    this.posEl.textContent = `P${position}`;

    // Lap
    const lapsToWin = state.laps_to_win || 5;
    if (raceMode === 'practice') {
      this.lapEl.textContent = `Practice L${myCar.completed_laps + 1}`;
    } else if (raceMode === 'elimination') {
      const seconds = Math.ceil(state.elimination_timer || 0);
      this.lapEl.textContent = `Elim ${seconds}s`;
    } else {
      this.lapEl.textContent = `Lap ${myCar.lap || 1}/${lapsToWin}`;
    }

    // Speed (convert game units to km/h-ish display)
    const kmh = Math.round(Math.abs(myCar.speed) * 1.2);
    this.speedEl.textContent = `${kmh} km/h`;
    this.speedEl.classList.toggle('is-fast', kmh > 260);

    this.timeEl.textContent = `${(myCar.current_lap_time || 0).toFixed(2)}s`;

    // Nitro bar
    const nitroPct = (myCar.nitro_amount / 100) * 100;
    this.nitroFill.style.width = `${nitroPct}%`;
    this.nitroFill.classList.toggle('is-low', nitroPct < 25);

    // Health bar
    const healthPct = (myCar.health / 100) * 100;
    this.healthFill.style.width = `${healthPct}%`;
    this.healthFill.style.background = healthPct > 50 ? '#47d17e' : healthPct > 25 ? '#ffb300' : '#ff5c5c';

    this._updateLeaderboard(sorted, myPlayerId, state.laps_to_win || 5, raceMode);
    this._drawMinimap(state, myPlayerId);
    this._updateWarning(myCar);
  }

  _sortCars(cars, raceMode = 'sprint') {
    return [...cars].sort((a, b) => {
      if (raceMode === 'elimination' && a.finished !== b.finished) {
        return a.finished ? 1 : -1;
      }
      if (b.completed_laps !== a.completed_laps) return b.completed_laps - a.completed_laps;
      if ((b.track_progress || 0) !== (a.track_progress || 0)) {
        return (b.track_progress || 0) - (a.track_progress || 0);
      }
      return (a.current_lap_time || 0) - (b.current_lap_time || 0);
    });
  }

  _updateLeaderboard(cars, myPlayerId, lapsToWin, raceMode) {
    if (!this.leaderboardEl) return;

    this.leaderboardEl.innerHTML = cars.map((car, index) => {
      const lap = Math.min(lapsToWin, car.completed_laps + 1);
      const name = this._escape(car.name || `Car ${car.id}`);
      const klass = car.id === myPlayerId ? ' class="is-player"' : '';
      let meta = `L${lap}/${lapsToWin}`;
      if (raceMode === 'practice') meta = `${Math.round((car.speed || 0) * 1.2)} km/h`;
      if (raceMode === 'elimination') meta = car.finished ? 'Out' : `L${car.completed_laps + 1}`;
      return `
        <li${klass}>
          <span class="lb-rank">${index + 1}</span>
          <span class="lb-name">${name}</span>
          <span class="lb-meta">${meta}</span>
        </li>
      `;
    }).join('');
  }

  _drawMinimap(state, myPlayerId) {
    const ctx = this.minimapCtx;
    const track = state.track;
    if (!ctx || !track?.centerline?.length || !state.cars) return;

    const w = this.minimapCanvas.width;
    const h = this.minimapCanvas.height;
    const pad = 14;
    const scale = Math.min(
      (w - pad * 2) / track.world_width,
      (h - pad * 2) / track.world_height
    );
    const ox = (w - track.world_width * scale) / 2;
    const oy = (h - track.world_height * scale) / 2;

    this._ensureMinimapTrack(track, w, h, scale, ox, oy);
    ctx.clearRect(0, 0, w, h);
    ctx.drawImage(this._minimapTrackCanvas, 0, 0);

    for (const car of state.cars) {
      const x = ox + car.x * scale;
      const y = oy + car.y * scale;
      const [r, g, b] = car.color || [255, 255, 255];
      ctx.beginPath();
      ctx.arc(x, y, car.id === myPlayerId ? 4.5 : 3.2, 0, Math.PI * 2);
      ctx.fillStyle = `rgb(${r},${g},${b})`;
      ctx.fill();
      ctx.lineWidth = car.id === myPlayerId ? 2 : 1;
      ctx.strokeStyle = car.id === myPlayerId ? '#ffffff' : 'rgba(0,0,0,0.65)';
      ctx.stroke();
    }
  }

  _updateWarning(car) {
    if (!this.warningEl) return;

    let text = '';
    if (car.wrong_way) text = 'Wrong way';
    else if (car.shortcut_warning) text = 'Shortcut penalty';
    else if (car.invalid_lap_warning) text = 'Checkpoint missed';

    this.warningEl.textContent = text;
    this.warningEl.classList.toggle('hidden', !text);
  }

  _ensureMinimapTrack(track, w, h, scale, ox, oy) {
    const key = `${track.layout_name}:${track.centerline.length}:${w}:${h}`;
    if (this._minimapTrackCanvas && this._minimapTrackKey === key) return;

    this._minimapTrackKey = key;
    this._minimapTrackCanvas = document.createElement('canvas');
    this._minimapTrackCanvas.width = w;
    this._minimapTrackCanvas.height = h;

    const ctx = this._minimapTrackCanvas.getContext('2d');
    ctx.fillStyle = 'rgba(9, 12, 16, 0.82)';
    ctx.fillRect(0, 0, w, h);

    const drawPath = () => {
      ctx.beginPath();
      ctx.moveTo(ox + track.centerline[0][0] * scale, oy + track.centerline[0][1] * scale);
      for (let i = 1; i < track.centerline.length; i++) {
        ctx.lineTo(ox + track.centerline[i][0] * scale, oy + track.centerline[i][1] * scale);
      }
      ctx.closePath();
    };

    drawPath();
    ctx.lineWidth = Math.max(8, track.road_half_width * 2 * scale);
    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    drawPath();
    ctx.lineWidth = Math.max(5, track.road_half_width * 1.35 * scale);
    ctx.strokeStyle = 'rgba(85, 93, 106, 0.95)';
    ctx.stroke();

    if (track.start_pos) {
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(ox + track.start_pos[0] * scale - 2, oy + track.start_pos[1] * scale - 2, 4, 4);
    }
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
}
