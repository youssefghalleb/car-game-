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
  text.textContent = value > 0 ? value : 'GO!';
}

function hideCountdown() {
  document.getElementById('countdown-overlay').classList.add('hidden');
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

const muteAudioBtn = document.getElementById('mute-audio-btn');
const volumeSlider = document.getElementById('volume-slider');
muteAudioBtn.addEventListener('click', () => {
  audio.setMuted(!audio.muted);
  muteAudioBtn.textContent = audio.muted ? 'Unmute' : 'Mute';
});
volumeSlider.addEventListener('input', () => {
  audio.setMasterVolume(Number(volumeSlider.value) / 100);
});

// Game loop: render + send input
function gameLoop(now = performance.now()) {
  if (currentState && currentState.cars && currentState.track) {
    renderer.render(currentState, myPlayerId);
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
