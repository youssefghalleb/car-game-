// ============================================================
// Canvas 2D Renderer - draws track, cars, and effects
// ============================================================

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.camera = { x: 0, y: 0, scale: 1 };
    this._trackCacheKey = null;
    this._trackCanvas = null;
    this._particles = [];
    this._lastCrashEvents = null;
    this._lastFrame = performance.now();
    this._smoothCars = new Map();
    this.resize();
  }

  resize() {
    this.canvas.width = window.innerWidth;
    this.canvas.height = window.innerHeight;
  }

  render(state, myPlayerId) {
    const ctx = this.ctx;
    const { cars, track } = state;

    if (!track || !cars) return;

    const now = performance.now();
    const dt = Math.min(0.05, (now - this._lastFrame) / 1000);
    this._lastFrame = now;

    this._queueCrashEffects(state.crash_events);

    const renderCars = this._smoothCarStates(cars, dt);

    // Center camera on player car
    const myCar = renderCars.find(c => c.id === myPlayerId) || renderCars[0];
    if (myCar) {
      const lead = Math.min(120, Math.max(0, myCar.speed || 0) * 0.35);
      const rad = (myCar.angle * Math.PI) / 180;
      const targetX = myCar.x + Math.cos(rad) * lead;
      const targetY = myCar.y + Math.sin(rad) * lead;
      this.camera.x += (targetX - this.camera.x) * 0.16;
      this.camera.y += (targetY - this.camera.y) * 0.16;
    }

    // Calculate scale to show a reasonable area
    this.camera.scale = Math.min(
      this.canvas.width / 1200,
      this.canvas.height / 800
    );
    this._clampCameraToTrack(track);

    ctx.save();
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Transform to camera space
    ctx.translate(this.canvas.width / 2, this.canvas.height / 2);
    ctx.scale(this.camera.scale, this.camera.scale);
    ctx.translate(-this.camera.x, -this.camera.y);

    // Draw track
    this._drawTrackCached(ctx, track);

    // Draw cars
    for (const car of renderCars) {
      this._drawCar(ctx, car, car.id === myPlayerId);
    }

    this._updateParticles(dt);
    this._drawParticles(ctx);

    ctx.restore();
  }

  _clampCameraToTrack(track) {
    const halfViewW = this.canvas.width / (2 * this.camera.scale);
    const halfViewH = this.canvas.height / (2 * this.camera.scale);

    if (track.world_width <= halfViewW * 2) {
      this.camera.x = track.world_width / 2;
    } else {
      this.camera.x = Math.max(
        halfViewW,
        Math.min(track.world_width - halfViewW, this.camera.x)
      );
    }

    if (track.world_height <= halfViewH * 2) {
      this.camera.y = track.world_height / 2;
    } else {
      this.camera.y = Math.max(
        halfViewH,
        Math.min(track.world_height - halfViewH, this.camera.y)
      );
    }
  }

  _smoothCarStates(cars, dt) {
    const liveIds = new Set(cars.map(c => c.id));
    for (const id of this._smoothCars.keys()) {
      if (!liveIds.has(id)) this._smoothCars.delete(id);
    }

    const alpha = 1 - Math.pow(0.0015, Math.min(0.05, dt));

    return cars.map(car => {
      let smooth = this._smoothCars.get(car.id);
      if (!smooth) {
        smooth = { ...car };
        this._smoothCars.set(car.id, smooth);
        return smooth;
      }

      const dist = Math.hypot(car.x - smooth.x, car.y - smooth.y);
      const snap = dist > 260 || car.destroyed || car.finished;
      if (snap) {
        Object.assign(smooth, car);
        return smooth;
      }

      smooth.x += (car.x - smooth.x) * alpha;
      smooth.y += (car.y - smooth.y) * alpha;
      smooth.angle = this._lerpAngle(smooth.angle, car.angle, alpha);

      for (const key of [
        'speed',
        'nitro_amount',
        'health',
        'lap',
        'completed_laps',
        'track_progress',
        'current_lap_time',
        'best_lap_time',
        'finished',
        'destroyed',
        'is_bot',
        'name',
        'color',
      ]) {
        smooth[key] = car[key];
      }

      return smooth;
    });
  }

  _lerpAngle(from, to, alpha) {
    let delta = ((to - from + 540) % 360) - 180;
    return (from + delta * alpha + 360) % 360;
  }

  _drawTrackCached(ctx, track) {
    const key = [
      track.layout_name,
      track.world_width,
      track.world_height,
      track.road_half_width,
      track.centerline?.length || 0,
    ].join(':');

    if (!this._trackCanvas || this._trackCacheKey !== key) {
      this._trackCacheKey = key;
      this._trackCanvas = document.createElement('canvas');
      this._trackCanvas.width = track.world_width;
      this._trackCanvas.height = track.world_height;
      this._drawTrack(this._trackCanvas.getContext('2d'), track);
    }

    ctx.drawImage(this._trackCanvas, 0, 0);
  }

  _drawTrack(ctx, track) {
    const { centerline, road_half_width, world_width, world_height } = track;
    if (!centerline || centerline.length < 2) return;

    // Background
    ctx.fillStyle = '#2f6a39';
    ctx.fillRect(0, 0, world_width, world_height);

    ctx.globalAlpha = 0.16;
    ctx.strokeStyle = '#214f2a';
    ctx.lineWidth = 2;
    for (let x = -world_height; x < world_width; x += 120) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + world_height, world_height);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    // Draw road border (white)
    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = road_half_width * 2 + 18;
    ctx.strokeStyle = '#d9d9d2';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = road_half_width * 2 + 6;
    ctx.strokeStyle = '#1f2329';
    ctx.stroke();

    // Draw road surface (gray)
    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = road_half_width * 2;
    ctx.strokeStyle = '#4d5056';
    ctx.stroke();

    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = 3;
    ctx.setLineDash([28, 34]);
    ctx.strokeStyle = 'rgba(255,255,255,0.26)';
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw start line
    this._drawStartLine(ctx, track);
  }

  _drawStartLine(ctx, track) {
    const { start_pos, start_basis, layout_name } = track;
    if (!start_pos || !start_basis) return;

    const [tx, ty, nx, ny] = start_basis;
    const halfLen = layout_name === 'track_2' ? 128 : 58;
    const thickness = layout_name === 'track_2' ? 32 : 20;
    const tile = layout_name === 'track_2' ? 20 : 14;

    const startX = start_pos[0] - nx * halfLen;
    const startY = start_pos[1] - ny * halfLen;

    for (let i = 0; i < Math.floor((halfLen * 2) / tile); i++) {
      for (let j = 0; j < 2; j++) {
        ctx.fillStyle = (i + j) % 2 === 0 ? '#ffffff' : '#141414';

        const x = startX + nx * tile * i;
        const y = startY + ny * tile * i;

        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + nx * tile, y + ny * tile);
        ctx.lineTo(x + nx * tile + tx * thickness, y + ny * tile + ty * thickness);
        ctx.lineTo(x + tx * thickness, y + ty * thickness);
        ctx.closePath();
        ctx.fill();
      }
    }
  }

  _drawCar(ctx, car, isPlayer) {
    const { x, y, angle, color, name, speed, nitro_amount, health } = car;
    const [r, g, b] = color;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((angle * Math.PI) / 180);

    const w = 38, h = 19;

    // Speed/nitro trail
    if ((speed || 0) > 110) {
      const alpha = Math.min(0.34, (speed - 90) / 520);
      ctx.fillStyle = `rgba(170, 220, 255, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(-w / 2, -h * 0.42);
      ctx.lineTo(-w / 2 - 26 - speed * 0.08, 0);
      ctx.lineTo(-w / 2, h * 0.42);
      ctx.closePath();
      ctx.fill();
    }

    if ((nitro_amount || 0) < 99 && (speed || 0) > 80) {
      ctx.fillStyle = 'rgba(255, 134, 61, 0.78)';
      ctx.beginPath();
      ctx.ellipse(-w / 2 - 6, 0, 11, 4, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // Shadow
    ctx.fillStyle = 'rgba(0, 0, 0, 0.32)';
    ctx.beginPath();
    ctx.roundRect(-w / 2 + 3, -h / 2 + 4, w, h, 5);
    ctx.fill();

    // Car body
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2, w, h, 5);
    ctx.fill();

    ctx.fillStyle = `rgba(255,255,255,${isPlayer ? 0.24 : 0.14})`;
    ctx.fillRect(-w / 2 + 5, -h / 2 + 3, w * 0.45, 3);

    // Nose and wheels
    ctx.fillStyle = 'rgba(20, 24, 30, 0.9)';
    ctx.fillRect(w / 2 - 9, -h / 2 + 2, 7, h - 4);
    ctx.fillRect(-w / 2 + 6, -h / 2 - 3, 8, 4);
    ctx.fillRect(-w / 2 + 6, h / 2 - 1, 8, 4);
    ctx.fillRect(w / 2 - 14, -h / 2 - 3, 8, 4);
    ctx.fillRect(w / 2 - 14, h / 2 - 1, 8, 4);

    // Highlight player car
    if (isPlayer) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.95)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(-w / 2 - 4, -h / 2 - 4, w + 8, h + 8, 7);
      ctx.stroke();
    }

    // Windshield
    ctx.fillStyle = 'rgba(128, 206, 255, 0.72)';
    ctx.fillRect(w / 5, -h / 3, w / 5, h * 2 / 3);

    if (health <= 35) {
      ctx.strokeStyle = 'rgba(255, 80, 80, 0.85)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(-4, -h / 2 + 2);
      ctx.lineTo(8, h / 2 - 2);
      ctx.stroke();
    }

    ctx.restore();

    // Name tag
    ctx.save();
    ctx.font = '600 11px Segoe UI, Arial';
    ctx.fillStyle = 'rgba(0,0,0,0.55)';
    ctx.textAlign = 'center';
    ctx.fillText(name || '', x + 1, y - 21);
    ctx.fillStyle = isPlayer ? '#ffffff' : '#d8dde8';
    ctx.fillText(name || '', x, y - 22);
    ctx.restore();
  }

  _queueCrashEffects(events) {
    if (!events || events === this._lastCrashEvents) return;
    this._lastCrashEvents = events;

    for (const ev of events) {
      const count = Math.min(16, 5 + Math.floor((ev.impact || 0) / 8));
      for (let i = 0; i < count; i++) {
        const angle = Math.random() * Math.PI * 2;
        const speed = 80 + Math.random() * 150 + (ev.impact || 0);
        this._particles.push({
          x: ev.x,
          y: ev.y,
          vx: Math.cos(angle) * speed,
          vy: Math.sin(angle) * speed,
          life: 0.25 + Math.random() * 0.25,
          maxLife: 0.5,
          radius: 2 + Math.random() * 3,
          color: Math.random() > 0.45 ? '255,190,70' : '210,215,220',
        });
      }
    }
  }

  _updateParticles(dt) {
    for (const p of this._particles) {
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.vx *= 0.92;
      p.vy *= 0.92;
      p.life -= dt;
    }
    this._particles = this._particles.filter(p => p.life > 0);
  }

  _drawParticles(ctx) {
    for (const p of this._particles) {
      const alpha = Math.max(0, p.life / p.maxLife);
      ctx.fillStyle = `rgba(${p.color}, ${alpha})`;
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.radius * alpha, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
