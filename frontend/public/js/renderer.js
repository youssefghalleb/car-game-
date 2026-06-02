// ============================================================
// Canvas 2D Renderer - draws track, cars, and effects
// ============================================================

export class Renderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.camera = { x: 0, y: 0, scale: 1, targetScale: 1 };
    this._trackCacheKey = null;
    this._trackCanvas = null;
    this._particles = [];
    this._skidMarks = [];
    this._lastCrashEvents = null;
    this._lastFrame = performance.now();
    this._smoothCars = new Map();
    this.resize();
  }

  resize() {
    // Keep the game smooth on phones and small laptops. Rendering at 2x DPR
    // makes the canvas do up to four times the pixel work every frame.
    this.dpr = 1;
    this.viewWidth = window.innerWidth;
    this.viewHeight = window.innerHeight;
    this.canvas.width = Math.floor(this.viewWidth * this.dpr);
    this.canvas.height = Math.floor(this.viewHeight * this.dpr);
    this.canvas.style.width = `${this.viewWidth}px`;
    this.canvas.style.height = `${this.viewHeight}px`;
  }

  render(state, myPlayerId, ghostSamples = null) {
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
      this.camera.x += (targetX - this.camera.x) * 0.14;
      this.camera.y += (targetY - this.camera.y) * 0.14;
    }

    const speed = Math.abs(myCar?.speed || 0);
    const baseScale = Math.min(this.viewWidth / 1180, this.viewHeight / 780);
    const zoomOut = 1 - Math.min(0.16, speed / 2600);
    this.camera.targetScale = baseScale * zoomOut;
    this.camera.scale += (this.camera.targetScale - this.camera.scale) * 0.06;
    this._clampCameraToTrack(track);

    ctx.save();
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Transform to camera space
    ctx.translate(this.canvas.width / 2, this.canvas.height / 2);
    ctx.scale(this.camera.scale, this.camera.scale);
    ctx.translate(-this.camera.x, -this.camera.y);

    // Draw track
    this._drawTrackCached(ctx, track);

    this._drawGhost(ctx, ghostSamples);

    // Draw cars
    for (const car of renderCars) {
      this._drawCar(ctx, car, car.id === myPlayerId);
    }

    this._queueDrivingEffects(renderCars, dt);
    this._updateParticles(dt);
    this._drawParticles(ctx);
    this._drawSkidMarks(ctx);

    ctx.restore();
  }

  _drawGhost(ctx, samples) {
    if (samples && !Array.isArray(samples)) {
      this._drawGhostPath(ctx, samples.session, '#53b7ff', 0.28);
      this._drawGhostPath(ctx, samples.personal, '#7cff9b', 0.42);
      return;
    }
    this._drawGhostPath(ctx, samples, '#7cff9b', 0.42);
  }

  _drawGhostPath(ctx, samples, color, alpha) {
    if (!samples || samples.length < 2) return;

    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = 5;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.setLineDash([12, 14]);
    ctx.beginPath();
    ctx.moveTo(samples[0].x, samples[0].y);
    for (let i = 1; i < samples.length; i++) {
      ctx.lineTo(samples[i].x, samples[i].y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    const tail = samples[samples.length - 1];
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(tail.x, tail.y, 10, 0, Math.PI * 2);
    ctx.fill();
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
        'wrong_way',
        'off_track_warning',
        'angular_velocity',
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

    const grass = ctx.createLinearGradient(0, 0, world_width, world_height);
    grass.addColorStop(0, '#2f7040');
    grass.addColorStop(0.48, '#255e34');
    grass.addColorStop(1, '#356f3c');
    ctx.fillStyle = grass;
    ctx.fillRect(0, 0, world_width, world_height);

    this._drawGrassTexture(ctx, world_width, world_height);
    this._drawTrackDecorations(ctx, track);

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = road_half_width * 2 + 38;
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.28)';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = road_half_width * 2 + 24;
    ctx.strokeStyle = '#d8d7ca';
    ctx.stroke();

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = road_half_width * 2 + 10;
    ctx.strokeStyle = '#22272f';
    ctx.stroke();

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = road_half_width * 2;
    ctx.strokeStyle = '#4a4f58';
    ctx.stroke();

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = Math.max(8, road_half_width * 1.25);
    ctx.strokeStyle = 'rgba(112, 118, 126, 0.45)';
    ctx.stroke();

    this._drawCurbs(ctx, track);

    this._pathTrack(ctx, centerline);
    ctx.lineWidth = 3;
    ctx.setLineDash([28, 34]);
    ctx.strokeStyle = 'rgba(255,255,255,0.24)';
    ctx.stroke();
    ctx.setLineDash([]);

    this._drawStartLine(ctx, track);
  }

  _pathTrack(ctx, centerline) {
    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
  }

  _drawGrassTexture(ctx, worldWidth, worldHeight) {
    ctx.save();
    ctx.globalAlpha = 0.14;
    ctx.strokeStyle = '#184b27';
    ctx.lineWidth = 2;
    for (let x = -worldHeight; x < worldWidth; x += 240) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x + worldHeight, worldHeight);
      ctx.stroke();
    }
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = '#78a957';
    for (let x = 100; x < worldWidth; x += 620) {
      for (let y = 90; y < worldHeight; y += 520) {
        const wobble = ((x * 17 + y * 13) % 47) - 24;
        ctx.beginPath();
        ctx.ellipse(x + wobble, y - wobble, 34, 12, 0.4, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  _drawCurbs(ctx, track) {
    const { centerline, road_half_width } = track;
    ctx.save();
    ctx.lineWidth = 8;
    ctx.lineCap = 'butt';
    for (let i = 0; i < centerline.length; i += 8) {
      const a = centerline[i];
      const b = centerline[(i + 1) % centerline.length];
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const len = Math.hypot(dx, dy);
      if (len < 1) continue;
      const nx = -dy / len;
      const ny = dx / len;
      const color = Math.floor(i / 8) % 2 === 0 ? '#e53935' : '#f4f4ea';
      ctx.strokeStyle = color;
      for (const side of [-1, 1]) {
        ctx.beginPath();
        ctx.moveTo(a[0] + nx * road_half_width * side, a[1] + ny * road_half_width * side);
        ctx.lineTo(b[0] + nx * road_half_width * side, b[1] + ny * road_half_width * side);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  _drawTrackDecorations(ctx, track) {
    const { centerline, road_half_width, world_width, world_height } = track;
    ctx.save();
    for (let i = 0; i < centerline.length; i += 34) {
      const p = centerline[i];
      const q = centerline[(i + 2) % centerline.length];
      const dx = q[0] - p[0];
      const dy = q[1] - p[1];
      const len = Math.hypot(dx, dy);
      if (len < 1) continue;
      const nx = -dy / len;
      const ny = dx / len;
      const side = i % 28 === 0 ? 1 : -1;
      const x = p[0] + nx * (road_half_width + 84) * side;
      const y = p[1] + ny * (road_half_width + 84) * side;
      if (x < 40 || y < 40 || x > world_width - 40 || y > world_height - 40) continue;

      if (i % 102 === 0) {
        this._drawFlag(ctx, x, y, i);
      } else if (i % 68 === 0) {
        this._drawTireStack(ctx, x, y);
      } else {
        this._drawCrowdBlock(ctx, x, y, i);
      }
    }
    ctx.restore();
  }

  _drawFlag(ctx, x, y, seed) {
    ctx.fillStyle = 'rgba(20, 22, 26, 0.45)';
    ctx.fillRect(x - 2, y - 5, 4, 34);
    ctx.fillStyle = seed % 2 === 0 ? '#ffd166' : '#53b7ff';
    ctx.beginPath();
    ctx.moveTo(x + 2, y - 4);
    ctx.lineTo(x + 35, y + 3);
    ctx.lineTo(x + 2, y + 12);
    ctx.closePath();
    ctx.fill();
  }

  _drawTireStack(ctx, x, y) {
    for (let i = 0; i < 4; i++) {
      ctx.fillStyle = i % 2 ? '#20242b' : '#111318';
      ctx.beginPath();
      ctx.arc(x + i * 9, y + (i % 2) * 5, 8, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  _drawCrowdBlock(ctx, x, y, seed) {
    ctx.fillStyle = 'rgba(18, 20, 24, 0.28)';
    ctx.fillRect(x - 18, y - 10, 44, 22);
    for (let i = 0; i < 5; i++) {
      const hue = ['#f4f4ea', '#ff8a3d', '#53b7ff', '#7cff9b'][Math.abs(seed + i) % 4];
      ctx.fillStyle = hue;
      ctx.fillRect(x - 14 + i * 8, y - 7 + (i % 2) * 8, 5, 5);
    }
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

    const w = 42, h = 20;

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
      const flame = 1 + Math.min(1.5, speed / 220);
      ctx.fillStyle = 'rgba(255, 134, 61, 0.82)';
      ctx.beginPath();
      ctx.ellipse(-w / 2 - 9, 0, 9 * flame, 4.5, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(255, 220, 120, 0.78)';
      ctx.beginPath();
      ctx.ellipse(-w / 2 - 8, 0, 5 * flame, 2.5, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    // Shadow
    ctx.fillStyle = 'rgba(0, 0, 0, 0.32)';
    ctx.beginPath();
    ctx.roundRect(-w / 2 + 3, -h / 2 + 4, w, h, 5);
    ctx.fill();

    // Rear and front wings
    ctx.fillStyle = 'rgba(18, 22, 28, 0.92)';
    ctx.fillRect(-w / 2 - 4, -h / 2 - 2, 9, h + 4);
    ctx.fillRect(w / 2 - 6, -h / 2 - 4, 9, h + 8);

    // Car body
    const bodyGradient = ctx.createLinearGradient(-w / 2, -h / 2, w / 2, h / 2);
    bodyGradient.addColorStop(0, `rgb(${Math.min(255, r + 34)},${Math.min(255, g + 34)},${Math.min(255, b + 34)})`);
    bodyGradient.addColorStop(0.52, `rgb(${r},${g},${b})`);
    bodyGradient.addColorStop(1, `rgb(${Math.max(0, r - 36)},${Math.max(0, g - 36)},${Math.max(0, b - 36)})`);
    ctx.fillStyle = bodyGradient;
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2, w, h, 5);
    ctx.fill();

    // Nose cone
    ctx.beginPath();
    ctx.moveTo(w / 2 + 10, 0);
    ctx.lineTo(w / 2 - 2, -h / 2 + 2);
    ctx.lineTo(w / 2 - 2, h / 2 - 2);
    ctx.closePath();
    ctx.fill();

    ctx.fillStyle = `rgba(255,255,255,${isPlayer ? 0.30 : 0.16})`;
    ctx.fillRect(-w / 2 + 6, -h / 2 + 3, w * 0.52, 3);

    // Nose and wheels
    ctx.fillStyle = 'rgba(20, 24, 30, 0.9)';
    for (const wx of [-w / 2 + 8, w / 2 - 13]) {
      ctx.beginPath();
      ctx.roundRect(wx, -h / 2 - 5, 10, 6, 2);
      ctx.roundRect(wx, h / 2 - 1, 10, 6, 2);
      ctx.fill();
      ctx.fillStyle = 'rgba(220, 228, 238, 0.28)';
      ctx.fillRect(wx + 2, -h / 2 - 3, 5, 1);
      ctx.fillRect(wx + 2, h / 2 + 1, 5, 1);
      ctx.fillStyle = 'rgba(20, 24, 30, 0.9)';
    }

    // Highlight player car
    if (isPlayer) {
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.92)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.roundRect(-w / 2 - 6, -h / 2 - 6, w + 16, h + 12, 8);
      ctx.stroke();
      ctx.strokeStyle = 'rgba(255, 209, 102, 0.55)';
      ctx.lineWidth = 1;
      ctx.stroke();
    }

    // Windshield
    ctx.fillStyle = 'rgba(128, 206, 255, 0.82)';
    ctx.beginPath();
    ctx.roundRect(1, -h / 3, 10, h * 2 / 3, 3);
    ctx.fill();

    ctx.fillStyle = 'rgba(14, 16, 20, 0.35)';
    ctx.fillRect(-w / 2 + 5, -1, w - 10, 2);

    if (health <= 35) {
      ctx.strokeStyle = 'rgba(255, 80, 80, 0.85)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(-4, -h / 2 + 2);
      ctx.lineTo(8, h / 2 - 2);
      ctx.moveTo(-12, h / 2 - 2);
      ctx.lineTo(0, -h / 2 + 3);
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

  _queueDrivingEffects(cars, dt) {
    for (const car of cars) {
      const speed = Math.abs(car.speed || 0);
      const turning = Math.abs(car.angular_velocity || 0);
      if (speed > 115 && turning > 105 && this._skidMarks.length < 48) {
        this._skidMarks.push({
          x: car.x,
          y: car.y,
          angle: car.angle,
          life: 1.6,
          maxLife: 1.6,
        });
        if (this._skidMarks.length > 48) this._skidMarks.shift();
      }

      if (car.off_track_warning && this._particles.length < 48 && Math.random() < 0.18) {
        const angle = Math.random() * Math.PI * 2;
        this._particles.push({
          x: car.x,
          y: car.y,
          vx: Math.cos(angle) * 45,
          vy: Math.sin(angle) * 45,
          life: 0.28,
          maxLife: 0.28,
          radius: 3 + Math.random() * 5,
          color: '180,145,88',
        });
      }
    }
    if (this._particles.length > 80) {
      this._particles.splice(0, this._particles.length - 80);
    }

    for (const mark of this._skidMarks) {
      mark.life -= dt;
    }
    this._skidMarks = this._skidMarks.filter(mark => mark.life > 0);
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

  _drawSkidMarks(ctx) {
    for (const mark of this._skidMarks) {
      const alpha = Math.max(0, mark.life / mark.maxLife) * 0.24;
      ctx.save();
      ctx.translate(mark.x, mark.y);
      ctx.rotate((mark.angle * Math.PI) / 180);
      ctx.fillStyle = `rgba(12, 14, 18, ${alpha})`;
      ctx.fillRect(-18, -12, 24, 3);
      ctx.fillRect(-18, 9, 24, 3);
      ctx.restore();
    }
  }
}
