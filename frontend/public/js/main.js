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
let bestGhostSamples = null;
let lastGhostSampleAt = 0;
let lastGhostLap = 0;
let lastInputSentAt = 0;
let lastInputPayload = '';
const INPUT_SEND_INTERVAL_MS = 1000 / 30;
const INPUT_HEARTBEAT_MS = 250;

// Handle screen transitions
function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
}

// Client event handlers
client.on('joined', (data) => {
  myPlayerId = data.player_id;
  lobby.onJoined(data);
  // Initialize audio on first user interaction (join click)
  audio.init();
});

client.on('state', (state) => {
  if (state.players) {
    playerInfo = state.players;
  }
  currentState = state;

  if (state.state === 'lobby') {
    lobby.updatePlayers(playerInfo);
    lobby.updateStartState(state);
  } else if (state.state === 'countdown') {
    showScreen('game-screen');
    renderer.resize();
    showCountdown(state.countdown);
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
      audio.updateEngine(myCar.speed);
      updateRaceAudioEvents(myCar);
      updateGhostRecording(state, myCar);
    }
    // Play crash sounds
    if (state.crash_events) {
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
  document.getElementById('countdown-overlay').classList.add('hidden');
  displayedCountdown = null;
}

function updateRaceAudioEvents(car) {
  if (lastCheckpoint !== null && car.checkpoint !== lastCheckpoint) {
    audio.playCheckpoint();
  }
  lastCheckpoint = car.checkpoint;

  if ((car.completed_laps || 0) > lastCompletedLaps) {
    audio.playLap();
  }
  lastCompletedLaps = car.completed_laps || 0;

  const nitroActive = (car.nitro_amount || 0) < 99 && car.speed > 40;
  if (nitroActive && !lastNitroActive) {
    audio.playNitro();
  }
  lastNitroActive = nitroActive;

  const warning = car.wrong_way || car.shortcut_warning || car.invalid_lap_warning;
  const now = performance.now();
  if (warning && now - lastWarningAt > 900) {
    audio.playWarning();
    lastWarningAt = now;
  }
}

function updateGhostRecording(state, car) {
  const soloGhostMode = state.race_mode === 'practice' || state.race_mode === 'time_trial';
  if (!soloGhostMode || !car || car.is_bot) return;

  const ghostKey = `carGameGhost:${state.track_id || state.track?.layout_name || 'track'}:${state.race_mode}`;
  if (!bestGhostSamples) {
    try {
      bestGhostSamples = JSON.parse(localStorage.getItem(ghostKey) || 'null');
    } catch (_) {
      bestGhostSamples = null;
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
    bestGhostSamples = ghostSamples.slice();
    localStorage.setItem(ghostKey, JSON.stringify(bestGhostSamples));
    ghostSamples = [];
  }
  lastGhostLap = completed;
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

document.getElementById('ghost-toggle-btn').addEventListener('click', (event) => {
  ghostEnabled = !ghostEnabled;
  event.currentTarget.textContent = ghostEnabled ? 'Ghost On' : 'Ghost Off';
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
    renderer.render(currentState, myPlayerId, ghostEnabled ? bestGhostSamples : null);
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
