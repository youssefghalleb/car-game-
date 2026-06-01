// ============================================================
// HUD - heads up display during race
// ============================================================

export class HUD {
  constructor() {
    this.posEl = document.getElementById('hud-position');
    this.lapEl = document.getElementById('hud-lap');
    this.speedEl = document.getElementById('hud-speed');
    this.nitroFill = document.getElementById('hud-nitro-fill');
    this.healthFill = document.getElementById('hud-health-fill');
  }

  update(state, myPlayerId) {
    if (!state.cars) return;

    const myCar = state.cars.find(c => c.id === myPlayerId);
    if (!myCar) return;

    // Position in race
    const sorted = [...state.cars].sort((a, b) => {
      if (b.completed_laps !== a.completed_laps) return b.completed_laps - a.completed_laps;
      return a.id - b.id;
    });
    const position = sorted.findIndex(c => c.id === myPlayerId) + 1;
    this.posEl.textContent = `P${position}`;

    // Lap
    const lapsToWin = state.laps_to_win || 5;
    this.lapEl.textContent = `Lap ${myCar.lap || 1}/${lapsToWin}`;

    // Speed (convert game units to km/h-ish display)
    const kmh = Math.round(Math.abs(myCar.speed) * 1.2);
    this.speedEl.textContent = `${kmh} km/h`;

    // Nitro bar
    const nitroPct = (myCar.nitro_amount / 100) * 100;
    this.nitroFill.style.width = `${nitroPct}%`;

    // Health bar
    const healthPct = (myCar.health / 100) * 100;
    this.healthFill.style.width = `${healthPct}%`;
    this.healthFill.style.background = healthPct > 50 ? '#47d17e' : healthPct > 25 ? '#ffb300' : '#ff5c5c';
  }
}
