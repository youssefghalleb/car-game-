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
let prevCountdown = null;

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
  currentState = state;
  console.log('[Main] State received:', state.state, state.state === 'countdown' ? `countdown=${state.countdown}` : '');

  if (state.state === 'lobby') {
    lobby.updatePlayers(state.players);
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
  } else if (state.state === 'finished') {
    showScreen('game-screen');
    hideCountdown();
    audio.stopEngine();
    audio.playVictory();
    showResults(state.leaderboard);
  }
});

client.on('error', (msg) => {
  lobby.showStatus(msg);
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
    `<li>${p.name} — ${p.laps} laps — ${p.time}s</li>`
  ).join('');
}

document.getElementById('back-to-lobby-btn').addEventListener('click', () => {
  document.getElementById('results-overlay').classList.add('hidden');
  showScreen('lobby-screen');
  audio.stopAll();
  client.disconnect();
});

// Game loop: render + send input
function gameLoop() {
  if (currentState && currentState.cars && currentState.track) {
    renderer.render(currentState, myPlayerId);
  }

  // Send input to server
  if (client.connected && myPlayerId) {
    const controls = input.getControls();
    client.sendInput(controls);
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
