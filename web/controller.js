(() => {
  // ============================================================
  // Contrôleur mobile du jeu
  // ============================================================
  // Ce fichier est exécuté dans le navigateur du téléphone.
  //
  // Il sert à :
  // - lire les capteurs d'orientation du téléphone
  // - transformer l'inclinaison en direction
  // - gérer les boutons tactiles : accélération, nitro, pause, son
  // - filtrer et stabiliser le signal
  // - envoyer les commandes au jeu avec WebSocket
  // ============================================================

  // Identifiant du joueur injecté par le serveur Python.
  const PLAYER_ID = window.PLAYER_ID || "1";

  // Niveau d'assistance de direction choisi dans le lobby.
  const STEER_ASSIST = window.STEER_ASSIST || "none";

  // ------------------------------------------------------------
  // Éléments HTML
  // ------------------------------------------------------------

  // États de connexion.
  const wsStatus = document.getElementById("wsStatus");
  const sensorStatus = document.getElementById("sensorStatus");

  // Boutons principaux.
  const enableMotionBtn = document.getElementById("enableMotionBtn");
  const pauseBtn = document.getElementById("pauseBtn");
  const muteBtn = document.getElementById("muteBtn");
  const recenterBtn = document.getElementById("recenterBtn");
  const throttleBtn = document.getElementById("throttleBtn");
  const nitroBtn = document.getElementById("nitroBtn");

  // Réglages du capteur.
  const axisBtn = document.getElementById("axisBtn");
  const invertBtn = document.getElementById("invertBtn");

  // Réglages audio.
  const audioPanel = document.getElementById("audioPanel");
  const volumeSlider = document.getElementById("volumeSlider");
  const volumeValue = document.getElementById("volumeValue");
  const volumeBar = document.getElementById("volumeBar");

  // Affichage des valeurs envoyées.
  const steerValue = document.getElementById("steerValue");
  const throttleValue = document.getElementById("throttleValue");
  const steerBar = document.getElementById("steerBar");
  const throttleBar = document.getElementById("throttleBar");
  const axisDbg = document.getElementById("axisDbg");

  // ------------------------------------------------------------
  // États internes du contrôleur
  // ------------------------------------------------------------

  // Connexion WebSocket.
  let ws = null;

  // Indique si les capteurs du téléphone sont activés.
  let sensorEnabled = false;

  // États des boutons maintenus.
  let throttlePressed = false;
  let nitroPressed = false;

  // Choix de l'axe utilisé pour tourner.
  // false = gamma, true = beta.
  let useBetaForSteer = false;

  // Inversion de la direction si le téléphone réagit à l'envers.
  let invertSteer = true;

  // Valeurs du capteur.
  let latestRawAxis = 0;
  let filteredAxis = 0;
  let neutralAxis = 0;

  // Signaux envoyés au PC pour affichage dans le graphe.
  let latestRawRelative = 0;
  let latestFilteredRelative = 0;

  // Temps utilisés pour le filtrage et la sécurité.
  let lastSensorTime = 0;
  let lastFrameTime = performance.now();
  let recenterLockUntil = 0;

  // Direction finale après assistance.
  let assistedSteer = 0;

  // ------------------------------------------------------------
  // Données envoyées au jeu
  // ------------------------------------------------------------

  const state = {
    // Direction entre -1 et 1.
    steer: 0,

    // Accélération entre 0 et 1.
    throttle: 0,

    // Freinage, non utilisé ici mais gardé pour le protocole.
    brake: 0,

    // Nitro activée ou non.
    nitro: false,

    // Demande de pause.
    pause_pressed: false,

    // Son coupé ou non.
    mute: false,

    // Volume général entre 0 et 1.
    volume: 1,

    // Demande de redémarrage.
    restart_pressed: false,
  };

  // ------------------------------------------------------------
  // Réglages du traitement du signal
  // ------------------------------------------------------------

  // Zone morte en degrés : ignore les petits mouvements.
  const DEADZONE_DEG = 5.5;

  // Inclinaison considérée comme braquage maximal.
  const FULL_TILT_DEG = 18.0;

  // Direction maximale envoyée au jeu.
  const MAX_STEER_OUTPUT = 0.90;

  // Coefficient du filtre passe-bas.
  const SENSOR_FILTER_ALPHA = 0.38;

  // Vitesses de réaction de la direction.
  const STEER_RISE_RATE = 9.0;
  const STEER_FALL_RATE = 10.5;
  const STEER_RETURN_RATE = 11.0;

  // Court délai après recentrage pour éviter un saut de signal.
  const RECENTER_LOCK_MS = 120;

  // Limite les sauts anormaux du capteur.
  const MAX_SENSOR_JUMP_PER_FRAME = 40.0;

  // ------------------------------------------------------------
  // Fonctions utilitaires
  // ------------------------------------------------------------

  function clamp(v, min, max) {
    // Limite une valeur entre min et max.
    return Math.max(min, Math.min(max, v));
  }

  function lerp(a, b, t) {
    // Interpolation linéaire utilisée pour le filtrage.
    return a + (b - a) * t;
  }

  function expoCurve(v, expo = 1.0) {
    // Rend la direction plus douce autour du centre.
    const s = Math.sign(v);
    return s * Math.pow(Math.abs(v), expo);
  }

  function moveToward(current, target, rate, dt) {
    // Déplace progressivement current vers target.
    const maxStep = rate * dt;
    const delta = target - current;

    if (Math.abs(delta) <= maxStep) {
      return target;
    }

    return current + Math.sign(delta) * maxStep;
  }

  // ------------------------------------------------------------
  // Interface utilisateur
  // ------------------------------------------------------------

  function updateAudioUI() {
    // Met à jour le bouton muet et la barre de volume.
    if (!muteBtn || !volumeSlider || !volumeValue || !volumeBar) return;

    const percent = Math.round(state.volume * 100);

    volumeValue.textContent = `${percent}%`;
    volumeBar.style.width = `${percent}%`;
    volumeSlider.value = percent;

    muteBtn.textContent = `Muet: ${state.mute ? "OUI" : "NON"}`;
    muteBtn.className = state.mute ? "toggle-on" : "toggle-off";
  }

  function updateUI() {
    // Met à jour toutes les valeurs visibles sur le téléphone.
    steerValue.textContent = state.steer.toFixed(2);
    throttleValue.textContent = state.throttle.toFixed(2);

    steerBar.style.width = `${Math.abs(state.steer) * 100}%`;
    throttleBar.style.width = `${state.throttle * 100}%`;

    axisBtn.textContent = `Axe: ${useBetaForSteer ? "BETA" : "GAMMA"}`;
    axisBtn.className = useBetaForSteer ? "toggle-on" : "toggle-off";

    invertBtn.textContent = `Direction inversée: ${invertSteer ? "OUI" : "NON"}`;
    invertBtn.className = invertSteer ? "toggle-on" : "toggle-off";

    updateAudioUI();
  }

  // ------------------------------------------------------------
  // WebSocket
  // ------------------------------------------------------------

  function connectWS() {
    // Ouvre une connexion WebSocket avec le serveur Python.
    const proto = location.protocol === "https:" ? "wss" : "ws";

    ws = new WebSocket(`${proto}://${location.host}/ws/${PLAYER_ID}`);

    ws.onopen = () => {
      // Connexion réussie.
      wsStatus.textContent = "connecté";
      wsStatus.className = "status-ok";
    };

    ws.onclose = () => {
      // Reconnexion automatique si la connexion est perdue.
      wsStatus.textContent = "déconnecté";
      wsStatus.className = "status-bad";

      setTimeout(connectWS, 1000);
    };

    ws.onerror = () => {
      // Erreur WebSocket.
      wsStatus.textContent = "erreur";
      wsStatus.className = "status-bad";
    };
  }

  function sendState() {
    // Envoie l'état actuel du contrôleur au jeu.
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({
      steer: state.steer,
      throttle: state.throttle,
      brake: 0,
      nitro: state.nitro,
      pause_pressed: state.pause_pressed,
      mute: state.mute,
      volume: state.volume,
      restart_pressed: state.restart_pressed,

      // Données capteurs envoyées au PC pour le graphe.
      raw_sensor: latestRawRelative,
      filtered_sensor: latestFilteredRelative,
      optimized_signal: state.steer,
    }));

    // Ces actions ne doivent être envoyées qu'une seule fois.
    state.pause_pressed = false;
    state.restart_pressed = false;
  }

  // ------------------------------------------------------------
  // Gestion de l'axe et du recentrage
  // ------------------------------------------------------------

  function getSteerAxis(beta, gamma) {
    // Choisit l'axe utilisé pour diriger la voiture.
    return useBetaForSteer ? beta : gamma;
  }

  function hardResetSteer() {
    // Remet la direction à zéro sans changer les boutons maintenus.
    assistedSteer = 0;
    state.steer = 0;
    state.throttle = throttlePressed ? 1.0 : 0.0;
    state.brake = 0.0;
    state.nitro = nitroPressed;

    updateUI();
  }

  function recenterNow() {
    // Définit la position actuelle du téléphone comme position neutre.
    neutralAxis = latestRawAxis;
    filteredAxis = latestRawAxis;

    latestRawRelative = 0;
    latestFilteredRelative = 0;

    hardResetSteer();

    // Court verrouillage pour éviter un saut juste après le recentrage.
    recenterLockUntil = performance.now() + RECENTER_LOCK_MS;

    axisDbg.textContent = "0.0";
  }

  // ------------------------------------------------------------
  // Conversion capteur -> direction
  // ------------------------------------------------------------

  function computeRawTargetSteer(relativeAxisDeg) {
    // Convertit une inclinaison en valeur de direction entre -1 et 1.
    let x = relativeAxisDeg;

    if (invertSteer) {
      x *= -1;
    }

    const absX = Math.abs(x);

    // Zone morte : petits mouvements ignorés.
    if (absX <= DEADZONE_DEG) {
      return 0;
    }

    // Normalisation de l'inclinaison.
    const normalized = clamp(
      (absX - DEADZONE_DEG) / Math.max(0.0001, FULL_TILT_DEG - DEADZONE_DEG),
      0,
      1
    );

    // Courbe de sensibilité.
    const curved = expoCurve(normalized, 1.0);

    return Math.sign(x) * curved * MAX_STEER_OUTPUT;
  }

  function applyAssist(targetSteer, dt) {
    // Applique une assistance de direction côté téléphone.
    if (STEER_ASSIST === "none") {
      assistedSteer = targetSteer;
      return targetSteer;
    }

    if (STEER_ASSIST === "medium") {
      // Assistance moyenne : signal adouci mais encore réactif.
      const shaped = expoCurve(targetSteer / MAX_STEER_OUTPUT, 1.18) * 0.82;
      const target = clamp(shaped, -0.82, 0.82);

      if (Math.abs(target) < 0.01) {
        assistedSteer = moveToward(assistedSteer, 0, 5.8, dt);
      } else if (Math.abs(target) > Math.abs(assistedSteer)) {
        assistedSteer = moveToward(assistedSteer, target, 4.2, dt);
      } else {
        assistedSteer = moveToward(assistedSteer, target, 6.0, dt);
      }

      return assistedSteer;
    }

    if (STEER_ASSIST === "full") {
      // Assistance forte : direction plus stable et moins sensible.
      const shaped = expoCurve(targetSteer / MAX_STEER_OUTPUT, 1.35) * 0.62;
      const target = clamp(shaped, -0.62, 0.62);

      if (Math.abs(target) < 0.01) {
        assistedSteer = moveToward(assistedSteer, 0, 6.5, dt);
      } else if (Math.abs(target) > Math.abs(assistedSteer)) {
        assistedSteer = moveToward(assistedSteer, target, 2.8, dt);
      } else {
        assistedSteer = moveToward(assistedSteer, target, 4.2, dt);
      }

      return assistedSteer;
    }

    // Sécurité si une valeur inconnue est reçue.
    assistedSteer = targetSteer;
    return targetSteer;
  }

  function safeAxisUpdate(rawAxis) {
    // Évite les variations irréalistes dues à un bug de capteur.
    const delta = rawAxis - latestRawAxis;

    if (Math.abs(delta) > MAX_SENSOR_JUMP_PER_FRAME) {
      rawAxis = latestRawAxis + Math.sign(delta) * MAX_SENSOR_JUMP_PER_FRAME;
    }

    latestRawAxis = rawAxis;

    return rawAxis;
  }

  function updateSteerFromSensor(beta, gamma) {
    // Met à jour la direction à partir des valeurs beta/gamma.
    const now = performance.now();

    // Temps entre deux mesures.
    const dt = Math.max(0.001, (now - lastFrameTime) / 1000.0);
    lastFrameTime = now;
    lastSensorTime = now;

    // Axe choisi par l'utilisateur.
    let rawAxis = getSteerAxis(beta, gamma);

    // Protection contre les sauts anormaux.
    rawAxis = safeAxisUpdate(rawAxis);

    // Pendant le recentrage, on force le retour progressif au centre.
    if (now < recenterLockUntil) {
      filteredAxis = rawAxis;

      latestRawRelative = 0;
      latestFilteredRelative = 0;

      assistedSteer = moveToward(
        assistedSteer,
        0,
        STEER_RETURN_RATE * 2.0,
        dt
      );

      if (Math.abs(assistedSteer) < 0.02) {
        assistedSteer = 0;
      }

      state.steer = assistedSteer;
      state.throttle = throttlePressed ? 1.0 : 0.0;
      state.brake = 0.0;
      state.nitro = nitroPressed;

      axisDbg.textContent = "0.0";

      updateUI();
      return;
    }

    // Filtre passe-bas : réduit les tremblements du capteur.
    filteredAxis = lerp(filteredAxis, rawAxis, SENSOR_FILTER_ALPHA);

    // Valeurs relatives à la position neutre.
    const rawRelative = rawAxis - neutralAxis;
    const filteredRelative = filteredAxis - neutralAxis;

    latestRawRelative = rawRelative;
    latestFilteredRelative = filteredRelative;

    axisDbg.textContent = filteredRelative.toFixed(1);

    // Conversion en direction finale.
    const rawTarget = computeRawTargetSteer(filteredRelative);
    const finalSteer = applyAssist(rawTarget, dt);

    state.steer = clamp(finalSteer, -1, 1);
    state.throttle = throttlePressed ? 1.0 : 0.0;
    state.brake = 0.0;
    state.nitro = nitroPressed;

    updateUI();
  }

  function handleOrientation(event) {
    // Récupère les angles du téléphone.
    const beta = typeof event.beta === "number" ? event.beta : 0;
    const gamma = typeof event.gamma === "number" ? event.gamma : 0;

    updateSteerFromSensor(beta, gamma);
  }

  // ------------------------------------------------------------
  // Activation des capteurs
  // ------------------------------------------------------------

  async function enableMotion() {
    // Demande l'autorisation d'utiliser les capteurs du téléphone.
    try {
      // Autorisation nécessaire sur iPhone/iOS.
      if (
        typeof DeviceOrientationEvent !== "undefined" &&
        typeof DeviceOrientationEvent.requestPermission === "function"
      ) {
        const res = await DeviceOrientationEvent.requestPermission();

        if (res !== "granted") {
          sensorStatus.textContent = "refusés";
          sensorStatus.className = "status-bad";
          return;
        }
      }

      // Autorisation éventuelle pour les événements de mouvement.
      if (
        typeof DeviceMotionEvent !== "undefined" &&
        typeof DeviceMotionEvent.requestPermission === "function"
      ) {
        const res = await DeviceMotionEvent.requestPermission();

        if (res !== "granted") {
          sensorStatus.textContent = "refusés";
          sensorStatus.className = "status-bad";
          return;
        }
      }

      // Ajout de l'écouteur une seule fois.
      if (!sensorEnabled) {
        window.addEventListener("deviceorientation", handleOrientation, true);
        sensorEnabled = true;
      }

      sensorStatus.textContent = "actifs";
      sensorStatus.className = "status-ok";

      enableMotionBtn.textContent = "Capteurs activés";
      enableMotionBtn.disabled = true;

      // Recentrage automatique juste après activation.
      setTimeout(() => {
        recenterNow();
      }, 120);

    } catch (err) {
      console.error(err);

      sensorStatus.textContent = "erreur";
      sensorStatus.className = "status-bad";
    }
  }

  // ------------------------------------------------------------
  // Boutons tactiles maintenus
  // ------------------------------------------------------------

  function bindHoldButton(button, onPress, onRelease) {
    // Permet à un bouton de fonctionner au tactile et à la souris.

    const release = (e) => {
      if (e) e.preventDefault();
      onRelease();
    };

    // Appui tactile.
    button.addEventListener("touchstart", (e) => {
      e.preventDefault();
      onPress();
    }, { passive: false });

    // Relâchement tactile.
    button.addEventListener("touchend", release, { passive: false });
    button.addEventListener("touchcancel", release, { passive: false });

    // Appui souris pour les tests sur PC.
    button.addEventListener("mousedown", (e) => {
      e.preventDefault();
      onPress();
    });

    button.addEventListener("mouseup", release);
    button.addEventListener("mouseleave", () => onRelease());
  }

  // ------------------------------------------------------------
  // Association des boutons
  // ------------------------------------------------------------

  enableMotionBtn.addEventListener("click", enableMotion);
  recenterBtn.addEventListener("click", recenterNow);

  pauseBtn.addEventListener("click", () => {
    // Envoie une demande de pause au jeu.
    state.pause_pressed = true;

    // Affiche ou cache le panneau audio.
    if (audioPanel) {
      audioPanel.classList.toggle("hidden");
    }
  });

  if (muteBtn) {
    muteBtn.addEventListener("click", () => {
      // Active ou désactive le mode muet.
      state.mute = !state.mute;
      updateAudioUI();
    });
  }

  if (volumeSlider) {
    volumeSlider.addEventListener("input", () => {
      // Convertit le slider 0-100 en volume 0-1.
      state.volume = clamp(Number(volumeSlider.value) / 100, 0, 1);
      updateAudioUI();
    });
  }

  axisBtn.addEventListener("click", () => {
    // Change l'axe utilisé pour la direction.
    useBetaForSteer = !useBetaForSteer;

    // Recentrage nécessaire après changement d'axe.
    recenterNow();
    updateUI();
  });

  invertBtn.addEventListener("click", () => {
    // Inverse le sens de la direction.
    invertSteer = !invertSteer;

    hardResetSteer();
    updateUI();
  });

  bindHoldButton(
    throttleBtn,
    () => {
      // Début accélération.
      throttlePressed = true;
      state.throttle = 1.0;

      updateUI();
    },
    () => {
      // Fin accélération.
      throttlePressed = false;
      state.throttle = 0.0;

      updateUI();
    }
  );

  bindHoldButton(
    nitroBtn,
    () => {
      // Début nitro.
      nitroPressed = true;
      state.nitro = true;
    },
    () => {
      // Fin nitro.
      nitroPressed = false;
      state.nitro = false;
    }
  );

  // ------------------------------------------------------------
  // Sécurité si les capteurs s'arrêtent
  // ------------------------------------------------------------

  setInterval(() => {
    const now = performance.now();
    const dt = 0.05;

    // Si aucun capteur n'a envoyé de valeur récemment,
    // on ramène progressivement la direction au centre.
    if (now - lastSensorTime > 250) {
      assistedSteer = moveToward(
        assistedSteer,
        0,
        STEER_RETURN_RATE,
        dt
      );

      if (Math.abs(assistedSteer) < 0.02) {
        assistedSteer = 0;
      }

      state.steer = assistedSteer;
      state.throttle = throttlePressed ? 1.0 : 0.0;
      state.brake = 0.0;
      state.nitro = nitroPressed;

      updateUI();
    }
  }, 50);

  // ------------------------------------------------------------
  // Démarrage du contrôleur
  // ------------------------------------------------------------

  // Connexion au serveur Python.
  connectWS();

  // Première mise à jour visuelle.
  updateUI();

  // Envoi des commandes environ 30 fois par seconde.
  setInterval(sendState, 1000 / 30);
})();