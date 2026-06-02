// ============================================================
// Web Audio API - Engine sounds, countdown, collisions
// ============================================================
// Replicates the Python AudioManager using Web Audio API.
// Engine sound uses layered oscillators blended by speed.
// ============================================================

export class AudioManager {
  constructor() {
    this.ctx = null;
    this.enabled = false;
    this.masterVolume = 1.0;
    this.effectsVolume = 1.0;
    this.muted = false;
    this.quality = 'high';

    // Engine state
    this.enginePlaying = false;
    this.engineLayers = {};
    this.engineGains = {};

    // Master gain
    this.masterGain = null;
    this.effectsGain = null;
  }

  /**
   * Must be called after a user gesture (click/touch) to unlock audio.
   */
  init() {
    if (this.ctx) return;

    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.masterGain = this.ctx.createGain();
      this.masterGain.connect(this.ctx.destination);
      this.effectsGain = this.ctx.createGain();
      this.effectsGain.connect(this.masterGain);
      this.enabled = true;
    } catch (e) {
      console.warn('[Audio] Web Audio not available:', e);
      this.enabled = false;
    }
  }

  resume() {
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  setMasterVolume(v) {
    this.masterVolume = Math.max(0, Math.min(1, v));
    if (this.masterGain) {
      this.masterGain.gain.setTargetAtTime(
        this.muted ? 0 : this.masterVolume, this.ctx.currentTime, 0.05
      );
    }
  }

  setMuted(muted) {
    this.muted = muted;
    this.setMasterVolume(this.masterVolume);
  }

  setEffectsVolume(v) {
    this.effectsVolume = Math.max(0, Math.min(1, v));
    if (this.effectsGain) {
      this.effectsGain.gain.setTargetAtTime(this.effectsVolume, this.ctx.currentTime, 0.05);
    }
  }

  setQuality(quality) {
    this.quality = quality === 'low' ? 'low' : 'high';
  }

  // ----------------------------------------------------------
  // Countdown beeps
  // ----------------------------------------------------------

  playCountdownBeep(number) {
    if (!this.enabled) return;
    const freqMap = { 3: 520, 2: 620, 1: 720 };
    this._playTone(freqMap[number] || 600, 0.12, 0.22);
  }

  playGo() {
    if (!this.enabled) return;
    this._playTone(920, 0.20, 0.30);
  }

  playVictory() {
    if (!this.enabled) return;
    const now = this.ctx.currentTime;
    this._playToneAt(660, 0.10, 0.20, now);
    this._playToneAt(880, 0.10, 0.20, now + 0.12);
    this._playToneAt(1040, 0.20, 0.20, now + 0.24);
  }

  playCheckpoint() {
    if (!this.enabled) return;
    this._playTone(780, 0.07, 0.12);
  }

  playLap() {
    if (!this.enabled) return;
    const now = this.ctx.currentTime;
    this._playToneAt(740, 0.08, 0.16, now);
    this._playToneAt(980, 0.12, 0.16, now + 0.09);
  }

  playNitro() {
    if (!this.enabled) return;
    const now = this.ctx.currentTime;
    this._playToneAt(420, 0.06, 0.12, now);
    this._playToneAt(1040, 0.18, 0.10, now + 0.04);
  }

  playWarning() {
    if (!this.enabled) return;
    const now = this.ctx.currentTime;
    this._playToneAt(180, 0.08, 0.16, now);
    this._playToneAt(180, 0.08, 0.14, now + 0.13);
  }

  playClick() {
    if (!this.enabled) return;
    this._playTone(640, 0.035, 0.06);
  }

  // ----------------------------------------------------------
  // Crash sound (noise burst)
  // ----------------------------------------------------------

  playCrash(impactStrength) {
    if (!this.enabled) return;

    const volume = Math.min(0.85, 0.18 + impactStrength / 140);
    const durationScale = this.quality === 'low' ? 0.6 : 1.0;
    const duration = (0.04 + Math.min(0.08, impactStrength / 500)) * durationScale;

    const bufferSize = Math.floor(this.ctx.sampleRate * duration);
    const buffer = this.ctx.createBuffer(1, bufferSize, this.ctx.sampleRate);
    const data = buffer.getChannelData(0);

    let last = 0;
    for (let i = 0; i < bufferSize; i++) {
      const t = i / bufferSize;
      const white = Math.random() * 2 - 1;
      last = 0.86 * last + 0.14 * white;
      const env = Math.max(0, 1 - t) ** 2;
      data[i] = last * env;
    }

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;

    const gain = this.ctx.createGain();
    gain.gain.value = volume;
    source.connect(gain);
    gain.connect(this.effectsGain);
    source.start();
    source.onended = () => { source.disconnect(); gain.disconnect(); };
  }

  // ----------------------------------------------------------
  // Engine sound (layered oscillators)
  // ----------------------------------------------------------

  updateEngine(speed) {
    if (!this.enabled) return;

    speed = Math.max(0, speed);

    if (speed < 4) {
      this.stopEngine();
      return;
    }

    if (!this.enginePlaying) {
      this._startEngine();
    }

    const weights = this._blendLayers(speed);
    const overall = 0.18 + 0.52 * Math.min(1, speed / 320);

    for (const layer of ['idle', 'low', 'mid', 'high']) {
      const vol = weights[layer] * overall;
      if (this.engineGains[layer]) {
        this.engineGains[layer].gain.setTargetAtTime(vol, this.ctx.currentTime, 0.05);
      }
    }
  }

  stopEngine() {
    if (!this.enginePlaying) return;

    for (const layer of ['idle', 'low', 'mid', 'high']) {
      if (this.engineLayers[layer]) {
        this.engineLayers[layer].stop();
        this.engineLayers[layer] = null;
      }
      if (this.engineGains[layer]) {
        this.engineGains[layer].disconnect();
        this.engineGains[layer] = null;
      }
    }
    this.enginePlaying = false;
  }

  stopAll() {
    this.stopEngine();
  }

  // ----------------------------------------------------------
  // Internal helpers
  // ----------------------------------------------------------

  _startEngine() {
    if (this.enginePlaying) return;

    const layerConfigs = {
      idle: { freq: 42, harmonics: [1.0, 0.45, 0.18] },
      low:  { freq: 58, harmonics: [1.0, 0.55, 0.22] },
      mid:  { freq: 82, harmonics: [1.0, 0.62, 0.28, 0.12] },
      high: { freq: 118, harmonics: [1.0, 0.70, 0.35, 0.18] },
    };

    for (const [name, cfg] of Object.entries(layerConfigs)) {
      const gain = this.ctx.createGain();
      gain.gain.value = 0;
      gain.connect(this.effectsGain);

      // Use a periodic wave built from harmonics
      const real = new Float32Array(cfg.harmonics.length + 1);
      const imag = new Float32Array(cfg.harmonics.length + 1);
      real[0] = 0;
      imag[0] = 0;
      for (let i = 0; i < cfg.harmonics.length; i++) {
        real[i + 1] = 0;
        imag[i + 1] = cfg.harmonics[i];
      }

      const wave = this.ctx.createPeriodicWave(real, imag, { disableNormalization: false });
      const osc = this.ctx.createOscillator();
      osc.setPeriodicWave(wave);
      osc.frequency.value = cfg.freq;
      osc.connect(gain);
      osc.start();

      this.engineLayers[name] = osc;
      this.engineGains[name] = gain;
    }

    this.enginePlaying = true;
  }

  _blendLayers(speed) {
    const s = Math.max(0, Math.min(320, speed));
    let idle = 0, low = 0, mid = 0, high = 0;

    if (s < 15) {
      idle = 0.55;
    } else if (s < 50) {
      const k = (s - 15) / 35;
      idle = 0.55 * (1 - k);
      low = 0.45 * k + 0.15;
    } else if (s < 110) {
      const k = (s - 50) / 60;
      low = 0.65 * (1 - k) + 0.25;
      mid = 0.55 * k;
    } else if (s < 190) {
      const k = (s - 110) / 80;
      low = 0.20 * (1 - k);
      mid = 0.65;
      high = 0.30 * k;
    } else {
      const k = (s - 190) / 130;
      mid = 0.65 * (1 - 0.35 * k);
      high = 0.25 + 0.55 * k;
    }

    return { idle, low, mid, high };
  }

  _playTone(freq, duration, volume) {
    this._playToneAt(freq, duration, volume, this.ctx.currentTime);
  }

  _playToneAt(freq, duration, volume, startTime) {
    const osc = this.ctx.createOscillator();
    osc.type = 'sine';
    osc.frequency.value = freq;

    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(volume, startTime);
    gain.gain.exponentialRampToValueAtTime(0.001, startTime + duration);

    osc.connect(gain);
    gain.connect(this.effectsGain);
    osc.start(startTime);
    osc.stop(startTime + duration + 0.01);
    osc.onended = () => { osc.disconnect(); gain.disconnect(); };
  }
}
