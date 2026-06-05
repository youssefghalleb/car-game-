(() => {
  const qs = new URLSearchParams(location.search);
  const els = {
    body: document.body,
    roomInput: document.getElementById('roomInput'),
    playerInput: document.getElementById('playerInput'),
    nameInput: document.getElementById('nameInput'),
    roomLabel: document.getElementById('roomLabel'),
    playerLabel: document.getElementById('playerLabel'),
    statusText: document.getElementById('statusText'),
    connectBtn: document.getElementById('connectBtn'),
    disconnectBtn: document.getElementById('disconnectBtn'),
    modeSelect: document.getElementById('modeSelect'),
    axisSelect: document.getElementById('axisSelect'),
    sensitivitySlider: document.getElementById('sensitivitySlider'),
    deadzoneSlider: document.getElementById('deadzoneSlider'),
    smoothingSlider: document.getElementById('smoothingSlider'),
    invertBtn: document.getElementById('invertBtn'),
    enableMotionBtn: document.getElementById('enableMotionBtn'),
    calibrateWizardBtn: document.getElementById('calibrateWizardBtn'),
    resetCalibrationBtn: document.getElementById('resetCalibrationBtn'),
    wizardText: document.getElementById('wizardText'),
    touchSteerSlider: document.getElementById('touchSteerSlider'),
    steerValue: document.getElementById('steerValue'),
    steerFill: document.getElementById('steerFill'),
    wheel: document.getElementById('wheel'),
    speedValue: document.getElementById('speedValue'),
    healthValue: document.getElementById('healthValue'),
    throttleBtn: document.getElementById('throttleBtn'),
    brakeBtn: document.getElementById('brakeBtn'),
    nitroBtn: document.getElementById('nitroBtn'),
    readyBtn: document.getElementById('readyBtn'),
    respawnBtn: document.getElementById('respawnBtn'),
    pauseBtn: document.getElementById('pauseBtn'),
    resumeBtn: document.getElementById('resumeBtn'),
    restartBtn: document.getElementById('restartBtn'),
    quitBtn: document.getElementById('quitBtn'),
    muteBtn: document.getElementById('muteBtn'),
    sfxBtn: document.getElementById('sfxBtn'),
    volumeSlider: document.getElementById('volumeSlider'),
    testVibrationBtn: document.getElementById('testVibrationBtn'),
    debugRoom: document.getElementById('debugRoom'),
    debugPlayer: document.getElementById('debugPlayer'),
    debugStatus: document.getElementById('debugStatus'),
    debugPing: document.getElementById('debugPing'),
    debugSteer: document.getElementById('debugSteer'),
    debugPedals: document.getElementById('debugPedals'),
    debugLastInput: document.getElementById('debugLastInput'),
    debugSocket: document.getElementById('debugSocket'),
  };

  const STORAGE_KEY = 'carGameControllerSettings';
  const INPUT_RATE_MS = 1000 / 30;
  const INPUT_HEARTBEAT_MS = 250;
  const CONNECT_DEBOUNCE_MS = 650;

  const settings = loadSettings();
  const state = {
    roomId: normalizeRoomId(qs.get('room') || ''),
    playerId: normalizePlayerId(qs.get('player') || ''),
    playerName: qs.get('name') || settings.name || 'Controller',
    status: 'disconnected',
    ws: null,
    connectSeq: 0,
    reconnectTimer: null,
    reconnectAttempts: 0,
    manualClose: false,
    joined: false,
    remoteClosedByReplace: false,
    connectLockedUntil: 0,
    configPromise: null,
    sensorEnabled: false,
    latestAxis: 0,
    rawSteer: 0,
    steer: 0,
    throttle: false,
    brake: false,
    nitro: false,
    ready: settings.ready ?? true,
    lastSent: '',
    lastSentAt: 0,
    lastInputLabel: '-',
    lastTelemetryState: '',
    lastTelemetryCountdown: null,
    lastTelemetryHealth: null,
    lastWarningVibrationAt: 0,
    lastNitro: false,
    vibrationPrimed: false,
    vibrationUnsupportedLogged: false,
    muted: !!settings.muted,
    sfxEnabled: settings.sfxEnabled !== false,
    volume: Number(settings.volume ?? 80),
    audioCtx: null,
    lastPingAt: 0,
    pingMs: null,
    calibrationStep: 'idle',
    calibration: settings.calibration || defaultCalibration(),
  };

  init();

  function init() {
    els.roomInput.value = state.roomId;
    els.playerInput.value = state.playerId;
    els.nameInput.value = state.playerName;
    els.modeSelect.value = settings.mode || 'tilt';
    els.axisSelect.value = settings.axis || 'gamma';
    els.sensitivitySlider.value = settings.sensitivity || 100;
    els.deadzoneSlider.value = settings.deadzone || 6;
    els.smoothingSlider.value = settings.smoothing ?? 35;
    els.volumeSlider.value = state.volume;

    bindEvents();
    updateReadyButton();
    updateInvertButton(settings.invert ?? true);
    updateAudioButtons();
    setStatus('disconnected', 'Not connected');
    updateLabels();
    updateSteeringUI(true);
    updateDebug();

    if (state.roomId && state.playerId) {
      setTimeout(() => connect(), 120);
    }
  }

  function bindEvents() {
    els.connectBtn.addEventListener('click', connect);
    els.disconnectBtn.addEventListener('click', disconnect);
    els.enableMotionBtn.addEventListener('click', enableMotion);
    els.calibrateWizardBtn.addEventListener('click', advanceCalibrationWizard);
    els.resetCalibrationBtn.addEventListener('click', resetCalibration);
    els.testVibrationBtn.addEventListener('click', () => {
      primeVibration([65, 35, 100]);
      playTone(620, 0.06, 'sine');
    });

    els.readyBtn.addEventListener('click', () => {
      state.ready = !state.ready;
      updateReadyButton();
      saveSettings();
      send({ action: 'ready', ready: state.ready }, true);
      haptic([35]);
    });
    els.respawnBtn.addEventListener('click', () => sendCommand('reset'));
    els.pauseBtn.addEventListener('click', () => sendCommand('pause'));
    els.resumeBtn.addEventListener('click', () => sendCommand('resume'));
    els.restartBtn.addEventListener('click', () => sendCommand('restart'));
    els.quitBtn.addEventListener('click', () => sendCommand('quit'));

    els.invertBtn.addEventListener('click', () => {
      updateInvertButton(!getInvert());
      saveSettings();
    });
    els.modeSelect.addEventListener('change', () => {
      if (els.modeSelect.value === 'touch') {
        state.rawSteer = Number(els.touchSteerSlider.value) / 100;
      }
      saveSettings();
    });
    [
      els.axisSelect,
      els.sensitivitySlider,
      els.deadzoneSlider,
      els.smoothingSlider,
      els.volumeSlider,
    ].forEach((el) => {
      el.addEventListener('input', saveSettings);
      el.addEventListener('change', saveSettings);
    });
    els.touchSteerSlider.addEventListener('input', () => {
      if (els.modeSelect.value === 'touch') {
        state.rawSteer = Number(els.touchSteerSlider.value) / 100;
        updateSteeringUI();
      }
    });

    els.muteBtn.addEventListener('click', () => {
      state.muted = !state.muted;
      updateAudioButtons();
      saveSettings();
    });
    els.sfxBtn.addEventListener('click', () => {
      state.sfxEnabled = !state.sfxEnabled;
      updateAudioButtons();
      saveSettings();
    });

    bindHold(els.throttleBtn, (value) => { state.throttle = value; });
    bindHold(els.brakeBtn, (value) => { state.brake = value; });
    bindHold(els.nitroBtn, (value) => { state.nitro = value; });

    document.addEventListener('contextmenu', (event) => event.preventDefault());
    window.addEventListener('pagehide', () => disconnect(true));

    setInterval(inputLoop, INPUT_RATE_MS);
  }

  function connect() {
    const now = performance.now();
    if (now < state.connectLockedUntil) return;
    state.connectLockedUntil = now + CONNECT_DEBOUNCE_MS;

    primeVibration(20);
    state.roomId = normalizeRoomId(els.roomInput.value);
    state.playerId = normalizePlayerId(els.playerInput.value);
    state.playerName = sanitizeName(els.nameInput.value);

    if (!state.roomId || !state.playerId) {
      setStatus('error', 'Pairing failed', 'Room ID and Player ID are required.');
      return;
    }

    els.roomInput.value = state.roomId;
    els.playerInput.value = state.playerId;
    els.nameInput.value = state.playerName;
    updateLabels();
    saveSettings();

    state.manualClose = false;
    state.remoteClosedByReplace = false;
    state.connectSeq += 1;
    const seq = state.connectSeq;

    clearReconnectTimer();
    closeSocket('replaced');
    state.joined = false;
    setStatus('connecting', 'Connecting');

    getWsBaseUrl().then((configuredWsBase) => {
      if (seq !== state.connectSeq) return;
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsBase = configuredWsBase || `${proto}//${location.host}`;
      const wsUrl = `${wsBase}/ws/${encodeURIComponent(state.roomId)}`;
      const ws = new WebSocket(wsUrl);
      state.ws = ws;
      updateDebug();

      ws.onopen = () => {
        if (seq !== state.connectSeq) return;
        setStatus('connecting', 'Connected', 'Pairing controller...');
        send({
          action: 'join',
          role: 'controller',
          player_id: state.playerId,
          name: state.playerName,
        }, true);
      };

      ws.onmessage = (event) => {
        if (seq !== state.connectSeq) return;
        handleMessage(event.data);
      };

      ws.onclose = (event) => {
        if (seq !== state.connectSeq) return;
        state.joined = false;
        state.remoteClosedByReplace = event.code === 4001 || event.reason === 'replaced';
        if (state.manualClose || state.remoteClosedByReplace) {
          setStatus('disconnected', 'Disconnected');
          return;
        }
        setStatus('disconnected', 'Disconnected');
        scheduleReconnect(event.code);
      };

      ws.onerror = () => {
        if (seq !== state.connectSeq) return;
        setStatus('error', 'Pairing failed', 'WebSocket error.');
      };
    }).catch(() => {
      setStatus('error', 'Pairing failed', 'Unable to read server config.');
    });
  }

  function disconnect(silent = false) {
    state.manualClose = true;
    state.connectSeq += 1;
    clearReconnectTimer();
    closeSocket('manual');
    state.joined = false;
    if (!silent) setStatus('disconnected', 'Disconnected');
  }

  function closeSocket(reason) {
    if (!state.ws) return;
    try {
      state.ws.onopen = null;
      state.ws.onmessage = null;
      state.ws.onerror = null;
      state.ws.onclose = null;
      if (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING) {
        state.ws.close(1000, reason);
      }
    } catch (_) {
      // Closing during navigation can throw in some mobile browsers.
    }
    state.ws = null;
  }

  function handleMessage(raw) {
    let data;
    try {
      data = JSON.parse(raw);
    } catch (_) {
      return;
    }

    if (data.action === 'joined') {
      state.joined = data.role === 'controller' && data.player_id === state.playerId;
      state.reconnectAttempts = 0;
      if (state.joined) {
        setStatus('paired', 'Controller paired');
        haptic([70, 30, 90]);
        playTone(740, 0.06, 'triangle');
        send({ action: 'ready', ready: state.ready }, true);
      } else {
        setStatus('error', 'Pairing failed', 'Server did not pair this controller.');
      }
      return;
    }

    if (data.error) {
      state.manualClose = true;
      setStatus('error', 'Pairing failed', formatError(data));
      haptic([120, 50, 120]);
      closeSocket('error');
      return;
    }

    if (data.type === 'telemetry') {
      handleTelemetry(data);
    }
  }

  function scheduleReconnect(code) {
    if (state.reconnectTimer || state.reconnectAttempts >= 8) return;
    state.reconnectAttempts += 1;
    const delay = Math.min(1000 * (2 ** (state.reconnectAttempts - 1)), 10000);
    setStatus('reconnecting', 'Reconnecting', `Retry ${state.reconnectAttempts} in ${Math.round(delay / 1000)}s`);
    state.reconnectTimer = setTimeout(() => {
      state.reconnectTimer = null;
      connect();
    }, delay);
    updateDebug();
  }

  function clearReconnectTimer() {
    if (!state.reconnectTimer) return;
    clearTimeout(state.reconnectTimer);
    state.reconnectTimer = null;
  }

  function send(payload, force = false) {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return false;
    if (!force && !state.joined) return false;

    const encoded = JSON.stringify(payload);
    const now = performance.now();
    if (!force && encoded === state.lastSent && now - state.lastSentAt < INPUT_HEARTBEAT_MS) {
      return false;
    }

    state.ws.send(encoded);
    state.lastSent = encoded;
    state.lastSentAt = now;

    if (payload.action === 'input') {
      state.lastInputLabel = `S ${payload.steer.toFixed(2)} T ${payload.throttle} B ${payload.brake} N ${payload.nitro ? 1 : 0}`;
      if (payload.nitro && !state.lastNitro) {
        haptic([55, 25, 55]);
        playTone(460, 0.05, 'sawtooth');
      }
      state.lastNitro = !!payload.nitro;
    } else {
      haptic(25);
      playTone(520, 0.035, 'sine');
    }

    updateDebug();
    return true;
  }

  function sendCommand(action) {
    send({ action }, true);
  }

  function inputLoop() {
    updateSteeringFromControls();
    updateSteeringUI();

    if (!state.joined) {
      updateDebug();
      return;
    }

    send({
      action: 'input',
      steer: roundInput(state.steer),
      throttle: state.throttle ? 1 : 0,
      brake: state.brake ? 1 : 0,
      nitro: state.nitro,
    });

    if (performance.now() - state.lastPingAt > 1000) {
      state.lastPingAt = performance.now();
    }
  }

  function updateSteeringFromControls() {
    if (els.modeSelect.value === 'touch') {
      state.rawSteer = Number(els.touchSteerSlider.value) / 100;
    }

    const smoothing = Number(els.smoothingSlider.value) / 100;
    const alpha = 1 - Math.min(0.92, smoothing);
    state.steer += (state.rawSteer - state.steer) * Math.max(0.1, alpha);
  }

  function computeTiltSteer(axisValue) {
    const axis = Number(axisValue) || 0;
    const calibration = state.calibration || defaultCalibration();
    const center = Number(calibration.center) || 0;
    const left = Number(calibration.left);
    const right = Number(calibration.right);
    const sensitivity = Number(els.sensitivitySlider.value) / 100;
    const deadzone = Number(els.deadzoneSlider.value) / 100;
    let normalized;

    if (Number.isFinite(left) && Number.isFinite(right) && Math.abs(left - center) > 1 && Math.abs(right - center) > 1) {
      if (axis < center) {
        normalized = -Math.abs((axis - center) / (left - center));
      } else {
        normalized = Math.abs((axis - center) / (right - center));
      }
    } else {
      normalized = (axis - center) / 18;
    }

    if (getInvert()) normalized *= -1;
    if (Math.abs(normalized) < deadzone) return 0;

    const sign = normalized >= 0 ? 1 : -1;
    const shaped = (Math.abs(normalized) - deadzone) / Math.max(0.001, 1 - deadzone);
    return clamp(sign * shaped * sensitivity, -1, 1);
  }

  function handleOrientation(event) {
    const axisName = els.axisSelect.value;
    state.latestAxis = Number(event[axisName]) || 0;
    if (els.modeSelect.value === 'tilt') {
      state.rawSteer = computeTiltSteer(state.latestAxis);
    }
  }

  async function enableMotion() {
    primeVibration([25, 25, 45]);
    if (typeof DeviceOrientationEvent !== 'undefined'
      && typeof DeviceOrientationEvent.requestPermission === 'function') {
      const result = await DeviceOrientationEvent.requestPermission();
      if (result !== 'granted') {
        setStatus('error', 'Pairing failed', 'Motion permission denied.');
        return;
      }
    }

    if (!state.sensorEnabled) {
      window.addEventListener('deviceorientation', handleOrientation, true);
      state.sensorEnabled = true;
    }
    els.enableMotionBtn.textContent = 'Motion On';
    els.enableMotionBtn.classList.add('success');
  }

  function advanceCalibrationWizard() {
    primeVibration(20);
    if (!state.sensorEnabled) {
      enableMotion();
    }

    if (state.calibrationStep === 'idle') {
      state.calibrationStep = 'center';
      els.wizardText.textContent = 'Step 1/4: hold the phone centered, then tap Save Center.';
      els.calibrateWizardBtn.textContent = 'Save Center';
      return;
    }

    if (state.calibrationStep === 'center') {
      state.calibration.center = state.latestAxis;
      state.calibrationStep = 'left';
      els.wizardText.textContent = 'Step 2/4: tilt left as far as comfortable, then tap Save Left.';
      els.calibrateWizardBtn.textContent = 'Save Left';
      haptic([35, 20, 35]);
      return;
    }

    if (state.calibrationStep === 'left') {
      state.calibration.left = state.latestAxis;
      state.calibrationStep = 'right';
      els.wizardText.textContent = 'Step 3/4: tilt right as far as comfortable, then tap Save Right.';
      els.calibrateWizardBtn.textContent = 'Save Right';
      haptic([35, 20, 35]);
      return;
    }

    state.calibration.right = state.latestAxis;
    state.calibrationStep = 'idle';
    els.wizardText.textContent = 'Step 4/4: calibration saved.';
    els.calibrateWizardBtn.textContent = 'Start Calibration';
    state.rawSteer = 0;
    state.steer = 0;
    els.touchSteerSlider.value = 0;
    saveSettings();
    haptic([50, 25, 90]);
  }

  function resetCalibration() {
    state.calibration = defaultCalibration();
    state.calibrationStep = 'idle';
    state.rawSteer = 0;
    state.steer = 0;
    els.touchSteerSlider.value = 0;
    els.wizardText.textContent = 'Calibration reset. Hold centered, then capture left and right tilt.';
    els.calibrateWizardBtn.textContent = 'Start Calibration';
    saveSettings();
    updateSteeringUI(true);
  }

  function handleTelemetry(data) {
    if (typeof data.speed === 'number') els.speedValue.textContent = String(Math.round(Math.abs(data.speed)));
    if (typeof data.health === 'number') els.healthValue.textContent = `${Math.round(data.health)}%`;

    if (typeof data.countdown === 'number' && data.countdown !== state.lastTelemetryCountdown) {
      if (data.countdown > 0) {
        haptic([45, 25, 45]);
        playTone(440 + data.countdown * 90, 0.06, 'square');
      } else {
        haptic([70, 35, 110]);
        playTone(820, 0.12, 'triangle');
      }
      state.lastTelemetryCountdown = data.countdown;
    }

    if (data.state !== state.lastTelemetryState) {
      if (data.state === 'racing') {
        haptic([80, 35, 120]);
        playTone(760, 0.1, 'triangle');
      }
      if (data.state === 'finished' || data.finished) {
        haptic([100, 55, 100, 55, 160]);
        playTone(920, 0.16, 'sine');
      }
      state.lastTelemetryState = data.state || '';
    }

    if (data.collision) {
      haptic([110, 35, 75]);
      playTone(180, 0.08, 'sawtooth');
    }

    if (data.wrong_way || data.shortcut_warning || data.invalid_lap_warning || data.off_track_warning) {
      const now = performance.now();
      if (now - state.lastWarningVibrationAt > 900) {
        state.lastWarningVibrationAt = now;
        haptic([50, 40, 50]);
        playTone(260, 0.05, 'square');
      }
    }

    if (
      state.lastTelemetryHealth !== null
      && typeof data.health === 'number'
      && data.health < state.lastTelemetryHealth - 2
    ) {
      haptic([95, 30, 60]);
    }
    if (typeof data.health === 'number') state.lastTelemetryHealth = data.health;
  }

  function bindHold(button, onChange) {
    const down = (event) => {
      event.preventDefault();
      primeVibration(18);
      button.classList.add('is-active');
      onChange(true);
    };
    const up = (event) => {
      if (event) event.preventDefault();
      button.classList.remove('is-active');
      onChange(false);
    };

    button.addEventListener('pointerdown', down, { passive: false });
    button.addEventListener('pointerup', up, { passive: false });
    button.addEventListener('pointercancel', up, { passive: false });
    button.addEventListener('pointerleave', up, { passive: false });
  }

  function setStatus(status, label, detail = '') {
    state.status = status;
    els.body.classList.remove('is-disconnected', 'is-connecting', 'is-reconnecting', 'is-paired', 'is-error');
    const className = {
      disconnected: 'is-disconnected',
      connecting: 'is-connecting',
      reconnecting: 'is-reconnecting',
      paired: 'is-paired',
      error: 'is-error',
    }[status] || 'is-disconnected';
    els.body.classList.add(className);
    els.body.classList.toggle('controller-locked', false);
    els.statusText.textContent = detail ? `${label} · ${detail}` : label;
    updateDebug();
  }

  function updateSteeringUI(force = false) {
    const steer = clamp(state.steer, -1, 1);
    if (!force && els.steerValue.textContent === steer.toFixed(2)) return;

    els.steerValue.textContent = steer.toFixed(2);
    els.wheel.style.setProperty('--steer-angle', String(Math.round(steer * 95)));

    const pct = Math.abs(steer) * 50;
    els.steerFill.style.width = `${pct}%`;
    els.steerFill.style.left = steer >= 0 ? '50%' : `${50 - pct}%`;
    els.steerFill.style.transform = 'none';
  }

  function updateReadyButton() {
    els.readyBtn.textContent = state.ready ? 'Ready' : 'Not Ready';
    els.readyBtn.classList.toggle('success', state.ready);
  }

  function updateInvertButton(invert) {
    els.invertBtn.dataset.invert = invert ? '1' : '0';
    els.invertBtn.textContent = `Invert: ${invert ? 'On' : 'Off'}`;
    els.invertBtn.classList.toggle('toggle-on', invert);
    els.invertBtn.classList.toggle('toggle-off', !invert);
  }

  function updateAudioButtons() {
    els.muteBtn.textContent = state.muted ? 'Unmute' : 'Mute';
    els.sfxBtn.textContent = `Effects: ${state.sfxEnabled ? 'On' : 'Off'}`;
    els.sfxBtn.classList.toggle('toggle-on', state.sfxEnabled);
    els.sfxBtn.classList.toggle('toggle-off', !state.sfxEnabled);
  }

  function updateLabels() {
    els.roomLabel.textContent = state.roomId || '-';
    els.playerLabel.textContent = state.playerId || '-';
  }

  function updateDebug() {
    els.debugRoom.textContent = state.roomId || '-';
    els.debugPlayer.textContent = state.playerId || '-';
    els.debugStatus.textContent = state.status;
    els.debugPing.textContent = state.pingMs === null ? '-' : `${state.pingMs}ms`;
    els.debugSteer.textContent = state.steer.toFixed(2);
    els.debugPedals.textContent = [
      state.throttle ? 'throttle' : '',
      state.brake ? 'brake' : '',
      state.nitro ? 'nitro' : '',
    ].filter(Boolean).join(' + ') || 'idle';
    els.debugLastInput.textContent = state.lastInputLabel;
    els.debugSocket.textContent = state.ws ? socketStateName(state.ws.readyState) : 'none';
  }

  function haptic(pattern) {
    if (!('vibrate' in navigator)) {
      if (!state.vibrationUnsupportedLogged) state.vibrationUnsupportedLogged = true;
      return false;
    }
    if (!state.vibrationPrimed) return false;
    return navigator.vibrate(pattern);
  }

  function primeVibration(pattern = 25) {
    state.vibrationPrimed = true;
    haptic(pattern);
  }

  function playTone(frequency, duration, type = 'sine') {
    if (state.muted || !state.sfxEnabled || Number(els.volumeSlider.value) <= 0) return;
    try {
      if (!state.audioCtx) {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (!AudioCtx) return;
        state.audioCtx = new AudioCtx();
      }
      const ctx = state.audioCtx;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = type;
      osc.frequency.value = frequency;
      gain.gain.value = (Number(els.volumeSlider.value) / 100) * 0.035;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + duration);
      osc.stop(ctx.currentTime + duration + 0.02);
    } catch (_) {
      // Audio is optional on controller devices.
    }
  }

  function getWsBaseUrl() {
    if (!state.configPromise) {
      state.configPromise = fetch('/api/config')
        .then((response) => (response.ok ? response.json() : {}))
        .then((config) => String(config.gameServerWsUrl || '').replace(/\/$/, ''))
        .catch(() => '');
    }
    return state.configPromise;
  }

  function saveSettings() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      name: sanitizeName(els.nameInput.value),
      mode: els.modeSelect.value,
      axis: els.axisSelect.value,
      sensitivity: els.sensitivitySlider.value,
      deadzone: els.deadzoneSlider.value,
      smoothing: els.smoothingSlider.value,
      invert: getInvert(),
      ready: state.ready,
      muted: state.muted,
      sfxEnabled: state.sfxEnabled,
      volume: Number(els.volumeSlider.value),
      calibration: state.calibration,
    }));
  }

  function loadSettings() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
    } catch (_) {
      return {};
    }
  }

  function defaultCalibration() {
    return { center: 0, left: -18, right: 18 };
  }

  function getInvert() {
    return els.invertBtn.dataset.invert !== '0';
  }

  function normalizeRoomId(value) {
    return String(value || '')
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, '')
      .slice(0, 32);
  }

  function normalizePlayerId(value) {
    return String(value || '')
      .trim()
      .toUpperCase()
      .replace(/[^A-Z0-9_-]/g, '')
      .slice(0, 12);
  }

  function sanitizeName(value) {
    return String(value || 'Controller').trim().slice(0, 20) || 'Controller';
  }

  function formatError(data) {
    if (data.blockers?.length) return data.blockers.join(' · ');
    if (data.error === 'player_not_found') return 'Player not found. Open the monitor first.';
    return String(data.error || 'Connection failed');
  }

  function socketStateName(value) {
    return ['connecting', 'open', 'closing', 'closed'][value] || 'unknown';
  }

  function roundInput(value) {
    return Math.round(clamp(value, -1, 1) * 1000) / 1000;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }
})();
