// ============================================================
// Input Handler - keyboard and touch controls
// ============================================================

export class InputHandler {
  constructor() {
    this._keys = {};
    this._touch = { throttle: false, brake: false, nitro: false };

    window.addEventListener('keydown', (e) => { this._keys[e.code] = true; });
    window.addEventListener('keyup', (e) => { this._keys[e.code] = false; });
  }

  enableTouch() {
    const throttleBtn = document.getElementById('touch-throttle');
    const brakeBtn = document.getElementById('touch-brake');
    const nitroBtn = document.getElementById('touch-nitro');

    const bind = (btn, key) => {
      btn.addEventListener('touchstart', (e) => { e.preventDefault(); this._touch[key] = true; });
      btn.addEventListener('touchend', (e) => { e.preventDefault(); this._touch[key] = false; });
      btn.addEventListener('touchcancel', (e) => { e.preventDefault(); this._touch[key] = false; });
    };

    bind(throttleBtn, 'throttle');
    bind(brakeBtn, 'brake');
    bind(nitroBtn, 'nitro');
  }

  getControls() {
    const steerLeft = this._keys['ArrowLeft'] || this._keys['KeyA'] ? 1 : 0;
    const steerRight = this._keys['ArrowRight'] || this._keys['KeyD'] ? 1 : 0;
    const throttle = this._keys['ArrowUp'] || this._keys['KeyW'] || this._touch.throttle ? 1 : 0;
    const brake = this._keys['ArrowDown'] || this._keys['KeyS'] || this._touch.brake ? 1 : 0;
    const nitro = this._keys['Space'] || this._touch.nitro;

    return {
      steer: steerRight - steerLeft,
      throttle,
      brake,
      nitro: !!nitro,
    };
  }
}
