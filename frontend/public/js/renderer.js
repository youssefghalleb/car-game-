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

    // Center camera on player car
    const myCar = cars.find(c => c.id === myPlayerId) || cars[0];
    if (myCar) {
      this.camera.x = myCar.x;
      this.camera.y = myCar.y;
    }

    // Calculate scale to show a reasonable area
    this.camera.scale = Math.min(
      this.canvas.width / 1200,
      this.canvas.height / 800
    );

    ctx.save();
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Transform to camera space
    ctx.translate(this.canvas.width / 2, this.canvas.height / 2);
    ctx.scale(this.camera.scale, this.camera.scale);
    ctx.translate(-this.camera.x, -this.camera.y);

    // Draw track
    this._drawTrack(ctx, track);

    // Draw cars
    for (const car of cars) {
      this._drawCar(ctx, car, car.id === myPlayerId);
    }

    ctx.restore();
  }

  _drawTrack(ctx, track) {
    const { centerline, road_half_width, world_width, world_height } = track;
    if (!centerline || centerline.length < 2) return;

    // Background
    ctx.fillStyle = '#2d5a30';
    ctx.fillRect(0, 0, world_width, world_height);

    // Draw road border (white)
    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = road_half_width * 2 + 10;
    ctx.strokeStyle = '#d2d2d2';
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    // Draw road surface (gray)
    ctx.beginPath();
    ctx.moveTo(centerline[0][0], centerline[0][1]);
    for (let i = 1; i < centerline.length; i++) {
      ctx.lineTo(centerline[i][0], centerline[i][1]);
    }
    ctx.closePath();
    ctx.lineWidth = road_half_width * 2;
    ctx.strokeStyle = '#484a4e';
    ctx.stroke();

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
    const { x, y, angle, color, is_bot, name, speed } = car;

    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((angle * Math.PI) / 180);

    // Car body
    const w = 32, h = 16;
    const [r, g, b] = color;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(-w / 2, -h / 2, w, h);

    // Highlight player car
    if (isPlayer) {
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.strokeRect(-w / 2 - 2, -h / 2 - 2, w + 4, h + 4);
    }

    // Windshield
    ctx.fillStyle = 'rgba(100, 180, 255, 0.6)';
    ctx.fillRect(w / 4, -h / 3, w / 5, h * 2 / 3);

    ctx.restore();

    // Name tag
    ctx.save();
    ctx.font = '10px Arial';
    ctx.fillStyle = isPlayer ? '#ffffff' : '#cccccc';
    ctx.textAlign = 'center';
    ctx.fillText(name || '', x, y - 16);
    ctx.restore();
  }
}
