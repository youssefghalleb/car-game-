// ============================================================
// Main entry point - wires together all game modules
// ============================================================

import { GameClient } from './client.js';
import { Renderer } from './renderer.js';
import { InputHandler } from './input.js';
import { LobbyUI } from './lobby.js';
import { HUD } from './hud.js';
import { AudioManager } from './audio.js';

const client = new GameClient();
const renderer = new Renderer(document.getElementById('game-canvas'));
const input = new InputHandler();
const lobby = new LobbyUI(client);
const hud = new HUD();
const audio = new AudioManager();

let currentState = null;
let myPlayerId = null;
let playerInfo = {};
let prevCountdown = null;
let displayedCountdown = null;
let lastCheckpoint = null;
let lastCompletedLaps = 0;
let lastNitroActive = false;
let lastWarningAt = 0;
let ghostEnabled = true;
let ghostSamples = [];
let personalGhost = null;
let sessionGhost = null;
let lastGhostSampleAt = 0;
let lastGhostLap = 0;
let lastLapStartTime = 0;
let raceStats = {
  maxSpeed: 0,
  nitroUses: 0,
  collisions: 0,
  cleanLap: true,
};
let lastInputSentAt = 0;
let lastInputPayload = '';
let activeScreenId = document.querySelector('.screen.active')?.id || null;
let lastRecordedFinishKey = '';
const INPUT_SEND_INTERVAL_MS = 1000 / 45;
const INPUT_HEARTBEAT_MS = 150;
const MAX_REASONABLE_RACE_RECORDS = 500;
const COUNT_BASED_ACHIEVEMENTS = new Set([
  'First Race',
  'First Win',
  '10 Wins',
  'Long Distance Driver',
]);

// Handle screen transitions
function showScreen(id) {
  if (activeScreenId === id) return false;
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  activeScreenId = id;
  return true;
}

// Client event handlers
client.on('joined', (data) => {
  myPlayerId = data.role === 'spectator' ? null : data.player_id;
  lobby.onJoined(data);
  // Initialize audio on first user interaction (join click)
  audio.init();
});

client.on('state', (state) => {
  if (state.players) {
    playerInfo = state.players;
  }
  currentState = state;
  updateGhostAvailability(state);

  if (state.state === 'lobby') {
    lobby.updatePlayers(playerInfo);
    lobby.updateStartState(state);
  } else if (state.state === 'countdown') {
    if (showScreen('game-screen')) {
      renderer.resize();
    }
    showCountdown(state.countdown);
    if (state.countdown === 3 && prevCountdown !== 3) {
      resetRaceTracking();
    }
    // Play countdown beeps
    if (state.countdown !== prevCountdown && state.countdown > 0 && state.countdown <= 3) {
      audio.playCountdownBeep(state.countdown);
    }
    if (state.countdown === 0 && prevCountdown !== 0) {
      audio.playGo();
    }
    prevCountdown = state.countdown;
  } else if (state.state === 'racing') {
    showScreen('game-screen');
    hideCountdown();
    hud.update(state, myPlayerId);
    // Update engine sound based on player speed
    const myCar = state.cars && state.cars.find(c => c.id === myPlayerId);
    if (myCar) {
      raceStats.maxSpeed = Math.max(raceStats.maxSpeed, Math.abs(myCar.speed || 0));
      audio.updateEngine(myCar.speed);
      updateRaceAudioEvents(myCar);
      updateGhostRecording(state, myCar);
    }
    // Play crash sounds
    if (state.crash_events) {
      raceStats.collisions += state.crash_events.length;
      raceStats.cleanLap = false;
      for (const ev of state.crash_events) {
        audio.playCrash(ev.impact);
      }
    }
  } else if (state.state === 'paused') {
    showScreen('game-screen');
    hideCountdown();
    hud.update(state, myPlayerId);
    audio.stopEngine();
  } else if (state.state === 'finished') {
    showScreen('game-screen');
    hideCountdown();
    audio.stopEngine();
    audio.playVictory();
    showResults(state.leaderboard);
    updatePersonalRecords(state);
  }
});

document.addEventListener('click', (event) => {
  if (event.target.closest('button, select, input')) {
    audio.init();
    audio.playClick();
  }
}, true);

client.on('error', (msg) => {
  if (typeof msg === 'object' && msg?.message) {
    lobby.showStatus(msg.message);
  } else {
    lobby.showStatus(msg);
  }
});

// Countdown
function showCountdown(value) {
  const overlay = document.getElementById('countdown-overlay');
  const text = document.getElementById('countdown-text');
  overlay.classList.remove('hidden');
  if (displayedCountdown !== value) {
    text.style.animation = 'none';
    // Force the animation to restart for each server-authoritative tick.
    void text.offsetWidth;
    text.style.animation = '';
    displayedCountdown = value;
  }
  text.textContent = value > 0 ? value : 'GO!';
  text.classList.toggle('is-go', value === 0);
}

function hideCountdown() {
  const overlay = document.getElementById('countdown-overlay');
  if (!overlay.classList.contains('hidden')) {
    overlay.classList.add('hidden');
  }
  displayedCountdown = null;
}

function updateRaceAudioEvents(car) {
  if (lastCheckpoint !== null && car.checkpoint !== lastCheckpoint) {
    audio.playCheckpoint();
  }
  lastCheckpoint = car.checkpoint;

  if ((car.completed_laps || 0) > lastCompletedLaps) {
    audio.playLap();
    lastLapStartTime = performance.now();
    raceStats.cleanLap = true;
  }
  lastCompletedLaps = car.completed_laps || 0;

  const nitroActive = (car.nitro_amount || 0) < 99 && car.speed > 40;
  if (nitroActive && !lastNitroActive) {
    raceStats.nitroUses += 1;
    audio.playNitro();
  }
  lastNitroActive = nitroActive;

  const warning = car.wrong_way || car.shortcut_warning || car.invalid_lap_warning || car.off_track_warning;
  const now = performance.now();
  if (warning && now - lastWarningAt > 900) {
    if (car.off_track_warning) audio.playOffTrack();
    audio.playWarning();
    lastWarningAt = now;
    raceStats.cleanLap = false;
  }

  if (Math.abs(car.angular_velocity || 0) > 92 && Math.abs(car.speed || 0) > 80) {
    audio.playTireScreech(Math.min(1, Math.abs(car.angular_velocity) / 220));
  }
}

function updateGhostRecording(state, car) {
  const soloGhostMode = state.race_mode === 'practice' || state.race_mode === 'time_trial';
  if (!soloGhostMode || !car || car.is_bot) return;

  const ghostKey = `carGameGhost:${state.track_id || state.track?.layout_name || 'track'}:${state.race_mode}`;
  if (!personalGhost) {
    try {
      personalGhost = JSON.parse(localStorage.getItem(ghostKey) || 'null');
    } catch (_) {
      personalGhost = null;
    }
  }

  const now = performance.now();
  if (now - lastGhostSampleAt >= 120) {
    lastGhostSampleAt = now;
    ghostSamples.push({ x: car.x, y: car.y });
    if (ghostSamples.length > 900) ghostSamples.shift();
  }

  const completed = car.completed_laps || 0;
  if (completed > lastGhostLap && ghostSamples.length > 8) {
    const lapTime = car.last_lap_time || ((performance.now() - lastLapStartTime) / 1000);
    const ghost = { lapTime, samples: ghostSamples.slice() };
    if (!sessionGhost || lapTime < sessionGhost.lapTime) {
      sessionGhost = ghost;
    }
    if (!personalGhost || lapTime < personalGhost.lapTime) {
      personalGhost = ghost;
      localStorage.setItem(ghostKey, JSON.stringify(personalGhost));
    }
    ghostSamples = [];
  }
  lastGhostLap = completed;
}

function resetRaceTracking() {
  lastCheckpoint = null;
  lastCompletedLaps = 0;
  lastNitroActive = false;
  lastRecordedFinishKey = '';
  ghostSamples = [];
  personalGhost = null;
  sessionGhost = null;
  lastGhostSampleAt = 0;
  lastGhostLap = 0;
  lastLapStartTime = performance.now();
  raceStats = { maxSpeed: 0, nitroUses: 0, collisions: 0, cleanLap: true };
}

function updatePersonalRecords(state) {
  if (!myPlayerId || !state.cars) return;
  const myCar = state.cars.find(c => c.id === myPlayerId);
  if (!myCar) return;
  const finishKey = getFinishRecordKey(state, myCar);
  if (!finishKey || finishKey === lastRecordedFinishKey) return;

  const records = sanitizeRecords(readPersonalRecords());
  if (records.recorded_finishes.includes(finishKey)) {
    lastRecordedFinishKey = finishKey;
    localStorage.setItem('carGameRecords', JSON.stringify(records));
    lobby.updateRecords();
    return;
  }

  const leaderboard = state.leaderboard || [];
  const position = leaderboard.findIndex(p => p.name === myCar.name);
  const rank = position >= 0 ? position + 1 : null;
  const achievements = new Set(records.achievements || []);

  records.races_completed = (records.races_completed || 0) + 1;
  if (rank === 1) records.wins = (records.wins || 0) + 1;
  if (rank && rank <= 3) records.podiums = (records.podiums || 0) + 1;
  if (myCar.best_lap_time) {
    records.best_lap = Math.min(records.best_lap || Infinity, myCar.best_lap_time);
  }
  if (myCar.total_time || leaderboard[0]?.time) {
    records.best_race_time = Math.min(records.best_race_time || Infinity, myCar.total_time || leaderboard[0].time);
  }

  achievements.add('First Race');
  if ((records.wins || 0) >= 1) achievements.add('First Win');
  if ((records.wins || 0) >= 10) achievements.add('10 Wins');
  if (raceStats.cleanLap && myCar.best_lap_time) achievements.add('Perfect Lap');
  if (raceStats.maxSpeed >= 240) achievements.add('Speed Demon');
  if (raceStats.nitroUses >= 5) achievements.add('Nitro Master');
  if ((records.races_completed || 0) >= 25) achievements.add('Long Distance Driver');

  records.achievements = [...achievements].sort();
  records.recorded_finishes = [finishKey, ...records.recorded_finishes].slice(0, 50);
  const cleanRecords = sanitizeRecords(records);
  lastRecordedFinishKey = finishKey;
  localStorage.setItem('carGameRecords', JSON.stringify(cleanRecords));
  lobby.updateRecords();
}

function getFinishRecordKey(state, myCar) {
  const leaderboard = state.leaderboard || [];
  if (!leaderboard.length) return '';
  const leaderboardKey = leaderboard
    .map(p => `${p.name}:${p.laps}:${p.time}`)
    .join('|');
  return [
    state.room_id || '',
    myPlayerId,
    state.track_id || state.settings?.track_layout || state.track?.layout_name || '',
    state.race_mode || state.settings?.race_mode || '',
    myCar.completed_laps || 0,
    myCar.total_time || '',
    myCar.best_lap_time || '',
    leaderboardKey,
  ].join('::');
}

function readPersonalRecords() {
  try {
    return JSON.parse(localStorage.getItem('carGameRecords') || '{}');
  } catch (_) {
    return {};
  }
}

function sanitizeRecords(records = {}) {
  const clean = { ...records };
  const races = safeCount(clean.races_completed);
  const wins = safeCount(clean.wins);
  const podiums = safeCount(clean.podiums);
  const corruptedCounts = [races, wins, podiums].some(count => count > MAX_REASONABLE_RACE_RECORDS)
    || wins > races
    || podiums > races;

  clean.races_completed = corruptedCounts ? 0 : races;
  clean.wins = corruptedCounts ? 0 : Math.min(wins, clean.races_completed);
  clean.podiums = corruptedCounts ? 0 : Math.min(Math.max(podiums, clean.wins), clean.races_completed);
  clean.best_lap = safeTime(clean.best_lap);
  clean.best_race_time = safeTime(clean.best_race_time);
  clean.achievements = Array.isArray(clean.achievements)
    ? [...new Set(clean.achievements.map(String))].sort()
    : [];
  if (corruptedCounts) {
    clean.achievements = clean.achievements.filter(name => !COUNT_BASED_ACHIEVEMENTS.has(name));
  }
  clean.recorded_finishes = !corruptedCounts && Array.isArray(clean.recorded_finishes)
    ? clean.recorded_finishes.map(String).filter(Boolean).slice(0, 50)
    : [];
  return clean;
}

function safeCount(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? Math.floor(numeric) : 0;
}

function safeTime(value) {
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric : undefined;
}

// Results
function showResults(leaderboard) {
  if (!leaderboard) return;
  const overlay = document.getElementById('results-overlay');
  const list = document.getElementById('results-list');
  overlay.classList.remove('hidden');
  list.innerHTML = leaderboard.map(p =>
    `<li>${p.name} - ${p.laps} laps - ${p.time}s</li>`
  ).join('');
}

document.getElementById('back-to-lobby-btn').addEventListener('click', () => {
  document.getElementById('results-overlay').classList.add('hidden');
  showScreen('lobby-screen');
  audio.stopAll();
  client.disconnect();
});

document.getElementById('pause-race-btn').addEventListener('click', () => client.pauseRace());
document.getElementById('resume-race-btn').addEventListener('click', () => client.resumeRace());
document.getElementById('restart-race-btn').addEventListener('click', () => {
  document.getElementById('results-overlay').classList.add('hidden');
  client.restartRace();
});
document.getElementById('reset-race-btn').addEventListener('click', () => client.resetRace());
document.getElementById('quit-race-btn').addEventListener('click', () => {
  audio.stopAll();
  client.quitRace();
  client.disconnect();
  showScreen('lobby-screen');
  window.location.reload();
});

const ghostToggleBtn = document.getElementById('ghost-toggle-btn');

function isSoloGhostMode(state = currentState) {
  const mode = state?.race_mode || state?.settings?.race_mode || null;
  const humanPlayerCount = Object.keys(playerInfo || {}).length;
  return (mode === 'practice' || mode === 'time_trial') && humanPlayerCount === 1;
}

function updateGhostAvailability(state = currentState) {
  const available = !!myPlayerId && isSoloGhostMode(state);
  ghostToggleBtn.classList.toggle('hidden', !available);
  ghostToggleBtn.disabled = !available;
  ghostToggleBtn.textContent = ghostEnabled ? 'Ghost On' : 'Ghost Off';

  if (!available) {
    ghostSamples = [];
    personalGhost = null;
    sessionGhost = null;
    lastGhostSampleAt = 0;
    lastGhostLap = 0;
  }
}

ghostToggleBtn.addEventListener('click', (event) => {
  if (!isSoloGhostMode()) return;
  ghostEnabled = !ghostEnabled;
  event.currentTarget.textContent = ghostEnabled ? 'Ghost On' : 'Ghost Off';
});

const helpOverlay = document.getElementById('help-overlay');
const helpButtons = [
  document.getElementById('help-btn'),
  document.getElementById('race-help-btn'),
].filter(Boolean);
const helpCloseBtn = document.getElementById('help-close-btn');

function openHelp() {
  if (!helpOverlay || !helpCloseBtn) return;
  helpOverlay.classList.remove('hidden');
  helpCloseBtn.focus();
}

function closeHelp() {
  if (!helpOverlay) return;
  helpOverlay.classList.add('hidden');
}

helpButtons.forEach(button => button.addEventListener('click', openHelp));
if (helpCloseBtn) helpCloseBtn.addEventListener('click', closeHelp);
if (helpOverlay) {
  helpOverlay.addEventListener('click', (event) => {
    if (event.target === helpOverlay) closeHelp();
  });
}
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && helpOverlay && !helpOverlay.classList.contains('hidden')) {
    closeHelp();
  }
});

const muteAudioBtn = document.getElementById('mute-audio-btn');
const volumeSlider = document.getElementById('volume-slider');
const effectsVolumeSlider = document.getElementById('effects-volume-slider');
const soundQualitySelect = document.getElementById('sound-quality-select');
muteAudioBtn.addEventListener('click', () => {
  audio.setMuted(!audio.muted);
  muteAudioBtn.textContent = audio.muted ? 'Unmute' : 'Mute';
});
volumeSlider.addEventListener('input', () => {
  audio.setMasterVolume(Number(volumeSlider.value) / 100);
});
effectsVolumeSlider.addEventListener('input', () => {
  audio.setEffectsVolume(Number(effectsVolumeSlider.value) / 100);
});
soundQualitySelect.addEventListener('change', () => {
  audio.setQuality(soundQualitySelect.value);
});

// Game loop: render + send input
function gameLoop(now = performance.now()) {
  if (currentState && currentState.cars && currentState.track) {
    const ghostPayload = ghostEnabled && isSoloGhostMode(currentState) && myPlayerId ? {
      personal: personalGhost?.samples || null,
      session: sessionGhost?.samples || null,
    } : null;
    renderer.render(currentState, myPlayerId, ghostPayload);
  }

  // Send input to server at a stable rate, with a small heartbeat for held keys.
  const controllerLinked = !!playerInfo?.[myPlayerId]?.controller;
  if (client.connected && myPlayerId && !controllerLinked) {
    const controls = input.getControls();
    const payload = JSON.stringify(controls);
    const due = now - lastInputSentAt >= INPUT_SEND_INTERVAL_MS;
    const changed = payload !== lastInputPayload;
    const heartbeat = now - lastInputSentAt >= INPUT_HEARTBEAT_MS;

    if (due && (changed || heartbeat)) {
      client.sendInput(controls);
      lastInputSentAt = now;
      lastInputPayload = payload;
    }
  }

  requestAnimationFrame(gameLoop);
}

// Start render loop
requestAnimationFrame(gameLoop);

// Handle window resize
window.addEventListener('resize', () => {
  if (document.getElementById('game-screen').classList.contains('active')) {
    renderer.resize();
  }
});

// Show mobile controls on touch devices
if ('ontouchstart' in window) {
  document.getElementById('mobile-controls').classList.remove('hidden');
  input.enableTouch();
}
