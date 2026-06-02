(() => {
  const qs = new URLSearchParams(location.search);
  const roomInput = document.getElementById('roomInput');
  const playerInput = document.getElementById('playerInput');
  const roomLabel = document.getElementById('roomLabel');
  const playerLabel = document.getElementById('playerLabel');
  const wsStatus = document.getElementById('wsStatus');
  const steerValue = document.getElementById('steerValue');
  const steerBar = document.getElementById('steerBar');
  const debugLog = document.getElementById('debugLog');

  roomInput.value = qs.get('room') || '';
  playerInput.value = qs.get('player') || '';

  let ws = null;
  let sensorEnabled = false;
  let throttle = false;
  let brake = false;
  let nitro = false;
  let invert = true;
  let neutral = 0;
  let latestAxis = 0;
  let steer = 0;
  let lastSent = '';
  let lastSentAt = 0;
  let connectSeq = 0;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let manualClose = false;
  let joined = false;
  let ready = true;
  let configPromise = null;
  let lastTelemetryState = '';
  let lastTelemetryCountdown = null;
  let lastTelemetryHealth = null;
  let lastNitro = false;

  const state = {
    roomId: roomInput.value.trim(),
    playerId: playerInput.value.trim(),
  };
  const savedSettings = JSON.parse(localStorage.getItem('carGameControllerSettings') || '{}');

  function clamp(v, min, max) {
    return Math.max(min, Math.min(max, v));
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

  function getWsBaseUrl() {
    if (!configPromise) {
      configPromise = fetch('/api/config')
        .then((response) => (response.ok ? response.json() : {}))
        .then((config) => String(config.gameServerWsUrl || '').replace(/\/$/, ''))
        .catch(() => '');
    }
    return configPromise;
  }

  function log(message, data = null) {
    const line = `[${new Date().toLocaleTimeString()}] ${message}${data ? ` ${JSON.stringify(data)}` : ''}`;
    console.info(`[Controller] ${message}`, data || '');
    if (debugLog) {
      debugLog.textContent = `${line}\n${debugLog.textContent}`.slice(0, 3000);
    }
  }

  function vibrate(pattern) {
    if ('vibrate' in navigator) {
      navigator.vibrate(pattern);
    }
  }

  function handleTelemetry(data) {
    if (typeof data.countdown === 'number' && data.countdown !== lastTelemetryCountdown) {
      if (data.countdown > 0) vibrate(35);
      else vibrate([45, 45, 90]);
      lastTelemetryCountdown = data.countdown;
    }

    if (data.state !== lastTelemetryState) {
      if (data.state === 'racing') vibrate([55, 35, 90]);
      if (data.state === 'finished') vibrate([80, 50, 80, 50, 140]);
      lastTelemetryState = data.state || '';
    }

    if (data.collision) vibrate([90, 35, 60]);
    if (data.wrong_way || data.shortcut_warning || data.invalid_lap_warning) vibrate([35, 35, 35]);

    if (lastTelemetryHealth !== null && typeof data.health === 'number' && data.health < lastTelemetryHealth - 2) {
      vibrate([80, 30, 50]);
    }
    if (typeof data.health === 'number') {
      lastTelemetryHealth = data.health;
    }
  }

  function saveSettings() {
    localStorage.setItem('carGameControllerSettings', JSON.stringify({
      mode: document.getElementById('modeSelect').value,
      axis: document.getElementById('axisSelect').value,
      sensitivity: document.getElementById('sensitivitySlider').value,
      deadzone: document.getElementById('deadzoneSlider').value,
      invert,
      neutral,
    }));
  }

  function applySavedSettings() {
    if (savedSettings.mode) document.getElementById('modeSelect').value = savedSettings.mode;
    if (savedSettings.axis) document.getElementById('axisSelect').value = savedSettings.axis;
    if (savedSettings.sensitivity) document.getElementById('sensitivitySlider').value = savedSettings.sensitivity;
    if (savedSettings.deadzone) document.getElementById('deadzoneSlider').value = savedSettings.deadzone;
    if (typeof savedSettings.invert === 'boolean') invert = savedSettings.invert;
    if (typeof savedSettings.neutral === 'number') neutral = savedSettings.neutral;
  }

  function connect() {
    state.roomId = normalizeRoomId(roomInput.value);
    state.playerId = normalizePlayerId(playerInput.value);
    if (!state.roomId || !state.playerId) return;

    roomInput.value = state.roomId;
    playerInput.value = state.playerId;

    roomLabel.textContent = state.roomId;
    playerLabel.textContent = state.playerId;
    log('connect_begin', { room: state.roomId, player: state.playerId });

    manualClose = false;
    connectSeq += 1;
    const seq = connectSeq;

    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    if (ws && ws.readyState !== WebSocket.CLOSED) {
      ws.onclose = null;
      ws.onerror = null;
      ws.close(1000, 'replaced');
    }

    joined = false;
    wsStatus.textContent = 'connecting';
    wsStatus.className = 'bad';

    getWsBaseUrl().then((configuredWsBase) => {
      if (seq !== connectSeq) return;
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsBase = configuredWsBase || `${proto}//${location.host}`;
      const wsUrl = `${wsBase}/ws/${encodeURIComponent(state.roomId)}`;
      log('ws_create', { url: wsUrl });
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
      if (seq !== connectSeq) return;
      wsStatus.textContent = 'joining';
      wsStatus.className = 'bad';
      log('ws_open');
      send({ action: 'join', role: 'controller', player_id: state.playerId, name: 'Controller' }, true);
      };
      ws.onmessage = (event) => {
      if (seq !== connectSeq) return;
      try {
        const data = JSON.parse(event.data);
        if (data.action === 'joined') {
          joined = true;
          reconnectAttempts = 0;
          wsStatus.textContent = 'connected';
          wsStatus.className = 'ok';
          log('pairing_success', data);
          send({ action: 'ready', ready }, true);
        } else if (data.error) {
          manualClose = true;
          wsStatus.textContent = data.error;
          wsStatus.className = 'bad';
          log('pairing_failure', data);
          ws.close(1000, data.error);
        } else if (data.type === 'telemetry') {
          handleTelemetry(data);
        }
      } catch (_) {
        // State broadcasts are ignored by the controller.
      }
      };
      ws.onclose = (event) => {
      if (seq !== connectSeq) return;
      joined = false;
      wsStatus.textContent = 'disconnected';
      wsStatus.className = 'bad';
      log('ws_close', { code: event.code, reason: event.reason || '' });
      const replaced = event.code === 4001 || event.reason === 'replaced';
      if (!manualClose && !replaced) scheduleReconnect(event.code);
      };
      ws.onerror = () => {
      if (seq !== connectSeq) return;
      wsStatus.textContent = 'error';
      wsStatus.className = 'bad';
      log('ws_error');
      };
    });
  }

  function scheduleReconnect(code) {
    if (reconnectTimer || reconnectAttempts >= 8) return;
    reconnectAttempts += 1;
    const delay = Math.min(1000 * (2 ** (reconnectAttempts - 1)), 10000);
    log('reconnect_scheduled', { delay, code });
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  }

  function send(payload, force = false) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (!force && !joined) return;
    const encoded = JSON.stringify(payload);
    if (!force && encoded === lastSent && performance.now() - lastSentAt < 250) return;
    ws.send(encoded);
    if (payload.action === 'input' && payload.nitro && !lastNitro) {
      vibrate(45);
    }
    if (payload.action === 'input') {
      lastNitro = !!payload.nitro;
    }
    lastSent = encoded;
    lastSentAt = performance.now();
    if (force || payload.action !== 'input') {
      log('send', payload);
    }
  }

  function updateUI() {
    steerValue.textContent = steer.toFixed(2);
    steerBar.style.width = `${Math.abs(steer) * 100}%`;
  }

  function computeSteer(axisValue) {
    const deadzone = Number(document.getElementById('deadzoneSlider').value);
    const sensitivity = Number(document.getElementById('sensitivitySlider').value) / 100;
    let value = axisValue - neutral;
    if (invert) value *= -1;
    if (Math.abs(value) <= deadzone) return 0;
    return clamp((value / 18) * sensitivity, -1, 1);
  }

  function handleOrientation(event) {
    const axisName = document.getElementById('axisSelect').value;
    latestAxis = Number(event[axisName]) || 0;
    if (document.getElementById('modeSelect').value === 'tilt') {
      steer = computeSteer(latestAxis);
      updateUI();
    }
  }

  function calibrate() {
    neutral = latestAxis;
    steer = 0;
    document.getElementById('touchSteerSlider').value = 0;
    updateUI();
    saveSettings();
  }

  async function enableMotion() {
    if (typeof DeviceOrientationEvent !== 'undefined'
      && typeof DeviceOrientationEvent.requestPermission === 'function') {
      const result = await DeviceOrientationEvent.requestPermission();
      if (result !== 'granted') return;
    }
    if (!sensorEnabled) {
      window.addEventListener('deviceorientation', handleOrientation, true);
      sensorEnabled = true;
      setTimeout(calibrate, 100);
    }
    document.getElementById('enableMotionBtn').textContent = 'Motion Enabled';
  }

  function bindHold(id, onChange) {
    const button = document.getElementById(id);
    const down = (event) => { event.preventDefault(); onChange(true); };
    const up = (event) => { if (event) event.preventDefault(); onChange(false); };
    button.addEventListener('touchstart', down, { passive: false });
    button.addEventListener('touchend', up, { passive: false });
    button.addEventListener('touchcancel', up, { passive: false });
    button.addEventListener('mousedown', down);
    button.addEventListener('mouseup', up);
    button.addEventListener('mouseleave', up);
  }

  document.getElementById('connectBtn').addEventListener('click', connect);
  document.getElementById('reconnectBtn').addEventListener('click', connect);
  document.getElementById('enableMotionBtn').addEventListener('click', enableMotion);
  document.getElementById('calibrateBtn').addEventListener('click', calibrate);
  document.getElementById('zeroSteerBtn').addEventListener('click', () => {
    steer = 0;
    document.getElementById('touchSteerSlider').value = 0;
    updateUI();
  });
  document.getElementById('readyBtn').addEventListener('click', (event) => {
    ready = !ready;
    event.currentTarget.textContent = ready ? 'Ready ✓' : 'Ready';
    event.currentTarget.className = ready ? 'toggle-on' : 'primary';
    send({ action: 'ready', ready }, true);
  });
  document.getElementById('invertBtn').addEventListener('click', (event) => {
    invert = !invert;
    event.currentTarget.textContent = `Invert: ${invert ? 'On' : 'Off'}`;
    event.currentTarget.className = invert ? 'toggle-on' : 'toggle-off';
    saveSettings();
  });
  ['modeSelect', 'axisSelect', 'sensitivitySlider', 'deadzoneSlider'].forEach(id => {
    const el = document.getElementById(id);
    el.addEventListener('change', saveSettings);
    el.addEventListener('input', saveSettings);
  });
  document.getElementById('touchSteerSlider').addEventListener('input', (event) => {
    if (document.getElementById('modeSelect').value === 'touch') {
      steer = Number(event.target.value) / 100;
      updateUI();
    }
  });
  document.getElementById('pauseBtn').addEventListener('click', () => send({ action: 'pause' }, true));
  document.getElementById('restartBtn').addEventListener('click', () => send({ action: 'restart' }, true));

  bindHold('throttleBtn', value => { throttle = value; });
  bindHold('brakeBtn', value => { brake = value; });
  bindHold('nitroBtn', value => { nitro = value; });

  setInterval(() => {
    if (document.getElementById('modeSelect').value === 'touch') {
      steer = Number(document.getElementById('touchSteerSlider').value) / 100;
      updateUI();
    }
    send({
      action: 'input',
      steer,
      throttle: throttle ? 1 : 0,
      brake: brake ? 1 : 0,
      nitro,
    });
  }, 1000 / 30);

  applySavedSettings();
  document.getElementById('invertBtn').textContent = `Invert: ${invert ? 'On' : 'Off'}`;
  document.getElementById('invertBtn').className = invert ? 'toggle-on' : 'toggle-off';
  document.getElementById('readyBtn').textContent = ready ? 'Ready ✓' : 'Ready';
  document.getElementById('readyBtn').className = ready ? 'toggle-on' : 'primary';

  updateUI();
  if (state.roomId && state.playerId) connect();
})();
